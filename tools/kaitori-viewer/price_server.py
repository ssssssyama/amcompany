"""ローカル価格収集APIサーバー

Chrome拡張からEC価格を受信し、cache_results.jsonに自動統合する。

使い方:
    python price_server.py
    python price_server.py --port 8502
"""

import argparse
import json
import logging
import re as _re
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

_MAX_BODY = 65_536  # リクエストボディ上限 (64KB)

from csv_loader import SHOP_NAMES, is_excluded, load_csv
from profit import calculate_cash_profit, is_above_threshold

_LOCAL_DATA_DIR = Path.home() / ".kaitori-viewer"
_LOCAL_DATA_DIR.mkdir(exist_ok=True)
CACHE_FILE = _LOCAL_DATA_DIR / "cache_results.json"
CSV_DIR = Path(__file__).resolve().parent.parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# 設定（デフォルト値、起動時に引数で上書き可能）
_config = {
    "threshold": 3000,
    "shipping": 1000,
    "rakuten_bonus": 10.0,
    "yahoo_bonus": 7.0,
    "shops": list(SHOP_NAMES),
}

_df = None

# --- クロールキュー（Chrome拡張自動巡回用） ---
# auto_extract.py が POST /crawl_queue で追加 → background.js が GET /crawl_queue でポーリング
_crawl_queue: list[dict] = []  # [{"jan": "...", "sites": ["ビックカメラ", ...]}]


def _get_df():
    global _df
    if _df is None:
        csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
        if csv_files:
            _df = load_csv(str(csv_files[0]))
            log.info("CSV読み込み: %s (%s件)", csv_files[0].name, len(_df))
    return _df


def _load_cache() -> list:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _default_json(obj):
    """numpy int64/float64 等をPython標準型に変換"""
    import numpy as np
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _save_cache(data: list):
    try:
        tmp = CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_default_json), encoding="utf-8")
        tmp.replace(CACHE_FILE)
    except OSError as e:
        log.warning("キャッシュ保存失敗: %s", e)


class PriceHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/add_price":
            self._handle_add_price()
        elif self.path == "/crawl_queue":
            self._handle_post_crawl_queue()
        elif self.path == "/debug_dom":
            self._handle_debug_dom()
        else:
            self._respond(404, {"error": "Not found"})

    def do_GET(self):
        if self.path == "/status":
            self._respond(200, {"status": "ok", "cache_count": len(_load_cache())})
        elif self.path == "/config":
            self._respond(200, _config)
        elif self.path.startswith("/crawl_targets"):
            self._handle_crawl_targets()
        elif self.path == "/crawl_queue":
            self._handle_get_crawl_queue()
        else:
            self._respond(404, {"error": "Not found"})

    def do_DELETE(self):
        if self.path == "/crawl_queue":
            global _crawl_queue
            count = len(_crawl_queue)
            _crawl_queue = []
            log.info("クロールキュー消費: %d件 → Chrome拡張が巡回開始", count)
            self._respond(200, {"cleared": count})
        else:
            self._respond(404, {"error": "Not found"})

    def do_OPTIONS(self):
        """CORSプリフライト対応"""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _handle_add_price(self):
        try:
            length = min(int(self.headers.get("Content-Length", 0)), _MAX_BODY)
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError):
            self._respond(400, {"error": "Invalid JSON"})
            return

        jan = str(body.get("jan", "")).strip()
        if not _re.fullmatch(r"\d{8}|\d{13}", jan):
            self._respond(400, {"error": "invalid JAN (8 or 13 digits required)"})
            return
        try:
            price = int(body.get("price", 0))
        except (ValueError, TypeError):
            self._respond(400, {"error": "invalid price"})
            return
        shop = body.get("shop", "")
        source = body.get("source", "手動")
        url = body.get("url", "")

        if price <= 0:
            self._respond(400, {"error": "price must be positive"})
            return

        # 買取CSVから商品情報を取得
        df = _get_df()
        if df is None:
            self._respond(500, {"error": "CSV not loaded"})
            return

        match = df[df["JAN"] == jan]
        if len(match) == 0:
            self._respond(404, {"error": f"JAN {jan} not found in CSV"})
            return

        row = match.iloc[0]

        # 除外フィルタ
        if is_excluded(row["商品名"], row.get("カテゴリ", "")):
            log.info("除外: JAN %s %s（除外対象商品）", jan, row["商品名"][:30])
            self._respond(200, {"action": "skipped", "reason": "excluded product"})
            return

        # 選択された買取店で最高値を取得
        kaitori = 0
        best_shop = ""
        for s in _config["shops"]:
            col = f"{s}_価格"
            if col in row.index and row[col] > kaitori:
                kaitori = row[col]
                best_shop = s

        if kaitori <= 0:
            kaitori = int(row["最高買取価格"])
            best_shop = row["最高値店舗"]

        # ボーナスポイント
        bonus_rates = {"楽天": _config["rakuten_bonus"], "Yahoo": _config["yahoo_bonus"]}
        bonus = int(price * bonus_rates.get(source, 0) / 100)
        pts = int(price * 0.01) + bonus  # 基本1% + ボーナス

        shipping = _config["shipping"]
        profit_info = calculate_cash_profit(kaitori, price, shipping, pts)

        new_item = {
            "JAN": jan,
            "商品名": row["商品名"],
            "最高買取価格": int(kaitori),
            "買取店": best_shop,
            "買取確認": row.get("買取確認", ""),
            "EC最安値": price,
            "EC店舗": shop,
            "ECソース": source,
            "EC URL": url,
            "ポイント": pts,
            "送料": shipping,
            "現金利益": profit_info["cash_profit"],
            "PT込利益": profit_info["profit_with_points"],
            "ROI(%)": profit_info["roi"],
            "stock_status": "in_stock",
            "在庫状況": "✅ 在庫あり",
            "商品リンク": url,
        }

        # キャッシュに追加（同一JANは安い方を優先）
        results = _load_cache()
        existing = [r for r in results if r.get("JAN") == jan]

        if existing and existing[0].get("EC最安値", 0) <= price:
            log.info("スキップ: JAN %s 既存EC価格 %s円 ≤ %s円 [%s]",
                     jan, f"{existing[0]['EC最安値']:,}", f"{price:,}", source)
            self._respond(200, {"action": "skipped", "reason": "existing price is lower", **new_item})
            return

        # 同一JAN削除 → 追加
        results = [r for r in results if r.get("JAN") != jan]
        results.append(new_item)
        _save_cache(results)

        log.info("追加: JAN %s %s円 [%s] 利益%s円 PT込%s円 %s",
                 jan, f"{price:,}", source,
                 f"{profit_info['cash_profit']:+,}", f"{profit_info['profit_with_points']:+,}",
                 row["商品名"][:30])

        self._respond(200, {"action": "added", **new_item})

    def _respond(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _handle_debug_dom(self):
        """DOM構造デバッグ情報を受信してログに出力する"""
        try:
            length = min(int(self.headers.get("Content-Length", 0)), _MAX_BODY)
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError):
            self._respond(400, {"error": "Invalid JSON"})
            return

        source = body.get("source", "?")
        url = body.get("url", "")[:80]
        log.info("=== DOM DEBUG: %s (%s) ===", source, url)
        for key in ["priceSelectors", "priceTexts", "genericPrice", "enPrice",
                     "bodySnippet", "priceElements", "allClasses"]:
            val = body.get(key)
            if val is not None:
                log.info("  %s: %s", key, str(val)[:500])
        self._respond(200, {"status": "logged"})

    def _handle_post_crawl_queue(self):
        """Chrome拡張自動巡回キューにJANを追加する

        POST /crawl_queue
        Body: {"janList": ["4549...", "4567..."], "sites": ["ビックカメラ", ...]}

        auto_extract.py がブロック済みサイトの JAN を投入し、
        Chrome拡張の background.js が GET /crawl_queue でポーリングして巡回する。
        """
        global _crawl_queue
        try:
            length = min(int(self.headers.get("Content-Length", 0)), _MAX_BODY)
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError):
            self._respond(400, {"error": "Invalid JSON"})
            return

        jan_list = body.get("janList", [])
        sites = body.get("sites", [])

        if not jan_list:
            self._respond(400, {"error": "janList is required"})
            return

        # キュー内の既存JANと重複しないように追加
        existing_jans = {item["jan"] for item in _crawl_queue}
        added = 0
        for jan in jan_list:
            jan = str(jan).strip()
            if jan and jan not in existing_jans:
                _crawl_queue.append({"jan": jan, "sites": sites})
                existing_jans.add(jan)
                added += 1

        log.info("クロールキュー追加: %d件 (合計%d件待ち)", added, len(_crawl_queue))
        self._respond(200, {
            "added": added,
            "queued": len(_crawl_queue),
        })

    def _handle_get_crawl_queue(self):
        """Chrome拡張がポーリングでクロールキューを取得する

        GET /crawl_queue
        → {"janList": [...], "sites": [...], "total": N}

        キュー内の全JANを返す。キューはクリアしない（peek方式）。
        Chrome拡張は巡回開始後に DELETE /crawl_queue でキューをクリアする。
        """
        if not _crawl_queue:
            self._respond(200, {"janList": [], "sites": [], "total": 0})
            return

        jan_list = [item["jan"] for item in _crawl_queue]
        all_sites: list[str] = []
        seen_sites: set[str] = set()
        for item in _crawl_queue:
            for s in item.get("sites", []):
                if s not in seen_sites:
                    all_sites.append(s)
                    seen_sites.add(s)

        self._respond(200, {
            "janList": jan_list,
            "sites": all_sites,
            "total": len(jan_list),
        })

    def _handle_crawl_targets(self):
        """利益候補JANリストを返す（Chrome拡張巡回用）

        GET /crawl_targets?top=50&min_kaitori=5000
        → { janList: ["4549292194036", ...], total: 50 }
        """
        from urllib.parse import urlparse as _up, parse_qs as _pq

        params = _pq(_up(self.path).query)
        top = int(params.get("top", ["50"])[0])
        min_kaitori = int(params.get("min_kaitori", ["5000"])[0])

        df = _get_df()
        if df is None:
            self._respond(500, {"error": "CSV not loaded"})
            return

        filtered = df[df["最高買取価格"] >= min_kaitori]
        filtered = filtered[~filtered.apply(
            lambda r: is_excluded(r["商品名"], r.get("カテゴリ", "")), axis=1
        )]

        sort_key = "利益候補スコア" if "利益候補スコア" in filtered.columns else "最高買取価格"
        targets = filtered.sort_values(sort_key, ascending=False).head(top)

        # 既にキャッシュ済みのJANを除外
        cached_jans = {r.get("JAN") for r in _load_cache() if r.get("JAN")}
        jan_list = [j for j in targets["JAN"].tolist() if j not in cached_jans]

        self._respond(200, {"janList": jan_list, "total": len(jan_list), "cached": len(cached_jans)})

    def _set_cors_headers(self):
        # サーバーは 127.0.0.1 のみでリッスンしているため外部からの接続は不可。
        # Content Script は ECサイトの Origin（例: https://www.biccamera.com）で
        # fetch を送るため、全Originを許可する必要がある。
        origin = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format, *args):
        pass  # デフォルトログを抑制（loggingで出力するため）


def main():
    parser = argparse.ArgumentParser(description="価格収集APIサーバー")
    parser.add_argument("--port", type=int, default=8502)
    parser.add_argument("--threshold", type=int, default=3000)
    parser.add_argument("--shipping", type=int, default=1000)
    parser.add_argument("--shops", nargs="*", default=None)
    args = parser.parse_args()

    _config["threshold"] = args.threshold
    _config["shipping"] = args.shipping
    if args.shops is not None:
        _config["shops"] = args.shops

    # CSV事前読み込み
    _get_df()

    server = HTTPServer(("127.0.0.1", args.port), PriceHandler)
    log.info("価格収集サーバー起動: http://127.0.0.1:%d", args.port)
    log.info("POST /add_price — Chrome拡張から価格を受信")
    log.info("GET  /status    — サーバー状態確認")
    log.info("Ctrl+C で停止")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("サーバー停止")
        server.server_close()


if __name__ == "__main__":
    main()
