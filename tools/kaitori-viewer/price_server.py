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

# run.py から起動された場合、共通ログファイルにも追記
try:
    from log_utils import attach_to_log_file as _attach_log
    _attach_log()
except Exception:
    pass

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
    """numpy/pandas の型を Python 標準型に変換してJSON化可能にする"""
    import numpy as np
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        # NaN は None に
        v = float(obj)
        if v != v:  # NaN check
            return None
        return v
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    # pandas Timestamp / Timedelta / NaT
    if hasattr(obj, "isoformat"):
        try:
            return obj.isoformat()
        except (ValueError, TypeError):
            pass
    # 最終フォールバック: .item() を持つ numpy scalar
    if hasattr(obj, "item") and callable(obj.item):
        try:
            return obj.item()
        except (ValueError, TypeError):
            pass
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _cache_lock():
    """プロセス間ファイルロック（filelock があれば使用、なければ no-op）"""
    import contextlib
    try:
        from filelock import FileLock
        return FileLock(str(CACHE_FILE) + ".lock", timeout=10)
    except ImportError:
        @contextlib.contextmanager
        def _nolock():
            yield
        return _nolock()


def _recalc_enrichment(item: dict, price: int, kaitori: int, source: str,
                       points: int, category: str = "") -> None:
    """価格変更時に enrichment フィールドを再計算（存在する場合のみ）

    auto_extract.py が追加していた以下の派生値は価格に依存するため、
    Chrome拡張が新しい最安値を返した場合は再計算が必要:
    - カード還元 / 実質利益 (ECソース依存)
    - 推奨売却先 / メルカリ想定売値 / メルカリ想定利益 / 売却差額 (EC価格依存)
    """
    shipping = _config.get("shipping", 1000)

    # カード還元 (auto_extract が計算していた場合のみ)
    if "カード還元" in item or "実質利益" in item:
        try:
            from profit import calculate_card_rebate
            card_rebate = calculate_card_rebate(price, source)
            item["カード還元"] = card_rebate
            cash_profit = item.get("現金利益", kaitori - price - shipping)
            item["実質利益"] = cash_profit + points + card_rebate
        except Exception:
            pass

    # メルカリ vs 買取店の売却チャネル判定
    if "推奨売却先" in item or "メルカリ想定売値" in item:
        try:
            from profit import decide_sell_channel
            channel = decide_sell_channel(
                kaitori_price=kaitori, ec_price=price,
                category=category, shipping_cost=shipping, points=points,
            )
            item["推奨売却先"] = "メルカリ" if channel["recommended"] == "mercari" else "買取店"
            item["メルカリ想定売値"] = channel["mercari_estimate"]
            item["メルカリ想定利益"] = channel["mercari_profit"]
            item["売却差額"] = channel["advantage"]
        except Exception:
            pass

    # backup_shops: 既存をそのまま保持（Chrome拡張のほうが更に安いので
    # 古い backup_shops に含まれるショップは新 EC 店舗より高い＝有効な
    # バックアップ候補として残す）


def _save_cache(data: list):
    """ロック付きアトミック保存"""
    try:
        with _cache_lock():
            tmp = CACHE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=_default_json), encoding="utf-8")
            tmp.replace(CACHE_FILE)
    except OSError as e:
        log.warning("キャッシュ保存失敗: %s", e)


# POST履歴ファイル（追記専用 JSON Lines）
POST_HISTORY_FILE = _LOCAL_DATA_DIR / "logs" / "post_history.jsonl"


def _log_post_event(
    *, jan: str, price: int, source: str, shop: str, url: str,
    action: str, reason: str = "", origin_header: str = "",
    extra: dict | None = None,
) -> None:
    """Chrome拡張/APIからのPOSTを履歴ファイルに追記する。

    キャッシュに入らなかったケース（suspicious ratio却下・除外対象・既存より高い）も
    記録されるため、「Chrome拡張が送信したか・反映されたか」を後から完全に検証可能。

    Args:
        action: "added" | "updated" | "skipped_ratio" | "skipped_existing_cheaper"
                | "skipped_excluded" | "invalid_jan" | "jan_not_in_csv" | "error"
        reason: action の追加情報
    """
    from datetime import datetime as _dt
    try:
        POST_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": _dt.now().isoformat(timespec="seconds"),
            "jan": jan,
            "price": price,
            "source": source,
            "shop": shop[:50],
            "url": url[:200],
            "action": action,
            "reason": reason[:200],
            "origin_header": origin_header[:200],
        }
        if extra:
            record.update(extra)
        with open(POST_HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=_default_json) + "\n")
    except OSError as e:
        log.warning("POST履歴書き込み失敗: %s", e)


# API トークン（書き込み系エンドポイントの簡易認証）
# ~/.kaitori-viewer/api_token が存在すればそれを使う。無ければ起動時に生成して保存。
_API_TOKEN_FILE = _LOCAL_DATA_DIR / "api_token"


def _get_or_create_api_token() -> str:
    """API トークンを取得（無ければ生成）"""
    import secrets
    if _API_TOKEN_FILE.exists():
        try:
            token = _API_TOKEN_FILE.read_text(encoding="utf-8").strip()
            if token:
                return token
        except OSError:
            pass
    token = secrets.token_urlsafe(32)
    try:
        _API_TOKEN_FILE.write_text(token, encoding="utf-8")
        # Unix なら 600 に (Windows は ACL の制約で無意味なので試行のみ)
        try:
            os.chmod(_API_TOKEN_FILE, 0o600)
        except OSError:
            pass
        log.info("APIトークンを生成: %s (Chrome拡張/auto_extractへ自動共有)", _API_TOKEN_FILE)
    except OSError as e:
        log.warning("APIトークン保存失敗: %s", e)
    return token


_API_TOKEN: str = ""  # startup() で初期化

# トークン認証が必要な書き込み系エンドポイント
_PROTECTED_PATHS = {"/add_price", "/crawl_queue", "/debug_dom"}


class PriceHandler(BaseHTTPRequestHandler):
    def _check_auth(self) -> bool:
        """保護対象エンドポイントでトークン検証。未認証なら 401 応答して False"""
        if self.path not in _PROTECTED_PATHS:
            return True
        # Chrome拡張の fetch にも付けやすい X-Kaitori-Token ヘッダを受け付ける
        token = (self.headers.get("X-Kaitori-Token", "")
                 or self.headers.get("Authorization", "").replace("Bearer ", ""))
        if _API_TOKEN and token != _API_TOKEN:
            # ローカルループバック (127.0.0.1) からのアクセスは無条件許可する
            # オプション: 環境変数 KAITORI_STRICT_AUTH=1 で localhost も認証必須に
            client_host = self.client_address[0] if self.client_address else ""
            strict = os.environ.get("KAITORI_STRICT_AUTH", "").lower() in ("1", "true", "yes")
            if strict or client_host not in ("127.0.0.1", "::1", "localhost"):
                log.warning("認証失敗: path=%s from=%s token=%s...",
                            self.path, client_host, token[:8])
                self._respond(401, {"error": "invalid or missing API token"})
                return False
        return True

    def do_POST(self):
        if not self._check_auth():
            return
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
        elif self.path == "/api_token":
            # ローカル（127.0.0.1）からのみ配布。Chrome拡張はこれを fetch して
            # 以降の POST に X-Kaitori-Token ヘッダを付ける。
            client = self.client_address[0] if self.client_address else ""
            if client in ("127.0.0.1", "::1", "localhost"):
                self._respond(200, {"token": _API_TOKEN})
            else:
                self._respond(403, {"error": "forbidden"})
        elif self.path == "/stats":
            self._handle_stats()
        elif self.path.startswith("/crawl_targets"):
            self._handle_crawl_targets()
        elif self.path == "/crawl_queue":
            self._handle_get_crawl_queue()
        elif self.path.startswith("/profit_check"):
            self._handle_profit_check()
        else:
            self._respond(404, {"error": "Not found"})

    def _handle_stats(self):
        """POST履歴の集計を返す（action別、ソース別、直近のエントリ）"""
        from collections import Counter
        stats = {
            "total_posts": 0,
            "by_action": {},
            "by_source": {},
            "cache_count": len(_load_cache()),
            "history_file": str(POST_HISTORY_FILE),
            "history_exists": POST_HISTORY_FILE.exists(),
            "recent": [],
        }
        if POST_HISTORY_FILE.exists():
            try:
                lines = POST_HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n")
                actions = Counter()
                sources_by_action = {}
                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    stats["total_posts"] += 1
                    a = rec.get("action", "?")
                    actions[a] += 1
                    sources_by_action.setdefault(a, Counter())[rec.get("source", "?")] += 1
                stats["by_action"] = dict(actions)
                stats["by_source"] = {a: dict(c) for a, c in sources_by_action.items()}
                # 最新10件
                tail = lines[-10:]
                stats["recent"] = [json.loads(l) for l in tail if l.strip()]
            except OSError:
                pass
        self._respond(200, stats)

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
        shop = body.get("shop", "")
        source = body.get("source", "手動")
        url = body.get("url", "")
        origin = self.headers.get("Origin", "") or self.headers.get("Referer", "")

        if not _re.fullmatch(r"\d{8}|\d{13}", jan):
            _log_post_event(jan=jan, price=0, source=source, shop=shop, url=url,
                            action="invalid_jan", reason="JAN format invalid",
                            origin_header=origin)
            self._respond(400, {"error": "invalid JAN (8 or 13 digits required)"})
            return
        try:
            price = int(body.get("price", 0))
        except (ValueError, TypeError):
            _log_post_event(jan=jan, price=0, source=source, shop=shop, url=url,
                            action="error", reason="invalid price value",
                            origin_header=origin)
            self._respond(400, {"error": "invalid price"})
            return

        # Chrome拡張からのリクエストを可視化（Origin/Referer ヘッダでサイト特定）
        log.info("受信: JAN %s 価格 %s円 ソース=%s 店舗=%s from=%s",
                 jan, f"{price:,}", source, shop[:30], origin[:80])

        if price <= 0:
            _log_post_event(jan=jan, price=price, source=source, shop=shop, url=url,
                            action="error", reason="price must be positive",
                            origin_header=origin)
            self._respond(400, {"error": "price must be positive"})
            return

        # 買取CSVから商品情報を取得
        df = _get_df()
        if df is None:
            _log_post_event(jan=jan, price=price, source=source, shop=shop, url=url,
                            action="error", reason="CSV not loaded", origin_header=origin)
            self._respond(500, {"error": "CSV not loaded"})
            return

        match = df[df["JAN"] == jan]
        if len(match) == 0:
            _log_post_event(jan=jan, price=price, source=source, shop=shop, url=url,
                            action="jan_not_in_csv",
                            reason=f"JAN {jan} not present in CSV",
                            origin_header=origin)
            self._respond(404, {"error": f"JAN {jan} not found in CSV"})
            return

        row = match.iloc[0]

        # 除外フィルタ
        if is_excluded(row["商品名"], row.get("カテゴリ", "")):
            log.info("除外: JAN %s %s（除外対象商品）", jan, row["商品名"][:30])
            _log_post_event(jan=jan, price=price, source=source, shop=shop, url=url,
                            action="skipped_excluded", reason="excluded product",
                            origin_header=origin,
                            extra={"product_name": str(row["商品名"])[:60]})
            self._respond(200, {"action": "skipped", "reason": "excluded product"})
            return

        # 選択された買取店で最高値を取得（表示用）
        max_kaitori = 0
        best_shop = ""
        for s in _config["shops"]:
            col = f"{s}_価格"
            if col in row.index and row[col] > max_kaitori:
                max_kaitori = row[col]
                best_shop = s

        if max_kaitori <= 0:
            max_kaitori = int(row["最高買取価格"])
            best_shop = row["最高値店舗"]

        # ハイブリッド: 利益判定は信頼買取価格（外れ値補正済み）ベース
        reliable_kaitori = int(row.get("信頼買取価格") or max_kaitori)
        is_outlier = bool(row.get("最高値_外れ値", False))
        kaitori = reliable_kaitori  # 判定・ratio チェックは reliable 基準

        # 価格比率の妥当性チェック（filters.py に集約）
        from filters import check_ratio as _check_ratio
        if kaitori > 0 and price > 0:
            rc = _check_ratio(int(kaitori), price)
            if rc["suspicious"]:
                log.warning("価格比率却下: JAN %s %s", jan, rc["reason"])
                _log_post_event(
                    jan=jan, price=price, source=source, shop=shop, url=url,
                    action="skipped_ratio",
                    reason=f"ratio {rc['ratio']} < threshold {rc['threshold']}",
                    origin_header=origin,
                    extra={"kaitori": int(kaitori), "product_name": str(row["商品名"])[:60]},
                )
                self._respond(200, {
                    "action": "skipped",
                    "reason": f"suspicious price ratio ({rc['ratio']} < {rc['threshold']})",
                })
                return

        # ボーナスポイント
        bonus_rates = {"楽天": _config["rakuten_bonus"], "Yahoo": _config["yahoo_bonus"]}
        bonus = int(price * bonus_rates.get(source, 0) / 100)
        pts = int(price * 0.01) + bonus  # 基本1% + ボーナス

        shipping = _config["shipping"]
        profit_info = calculate_cash_profit(kaitori, price, shipping, pts)

        from datetime import datetime as _dt
        upside_bonus = max_kaitori - reliable_kaitori
        new_item = {
            "JAN": jan,
            "商品名": row["商品名"],
            "最高買取価格": int(max_kaitori),  # 表示は最高値
            "買取店": best_shop,
            "信頼買取価格": int(reliable_kaitori),
            "上振れ余地": int(upside_bonus),
            "最高値_外れ値": is_outlier,
            "買取確認": row.get("買取確認", ""),
            "EC最安値": price,
            "EC店舗": shop,
            "ECソース": source,
            "EC URL": url,
            "ポイント": pts,
            "送料": shipping,
            "現金利益": profit_info["cash_profit"],  # 信頼価格ベース
            "PT込利益": profit_info["profit_with_points"],
            "ROI(%)": profit_info["roi"],
            "上振れ時利益": profit_info["cash_profit"] + int(upside_bonus),
            "stock_status": "in_stock",
            "在庫状況": "✅ 在庫あり",
            "商品リンク": url,
            "取得日時": _dt.now().strftime("%m/%d %H:%M"),
            # Chrome拡張由来の識別マーカー（run.py のサマリで分類に利用）
            "origin": "chrome_extension",
        }

        # read-modify-write をプロセス間ロックで保護（auto_extract 同時書き込み対策）
        with _cache_lock():
            results = _load_cache()
            existing = [r for r in results if r.get("JAN") == jan]

            if existing and existing[0].get("EC最安値", 0) <= price:
                log.info("スキップ: JAN %s 既存EC価格 %s円 ≤ %s円 [%s]",
                         jan, f"{existing[0]['EC最安値']:,}", f"{price:,}", source)
                _log_post_event(
                    jan=jan, price=price, source=source, shop=shop, url=url,
                    action="skipped_existing_cheaper",
                    reason=f"existing {existing[0].get('EC最安値',0)}円 ≤ new {price}円",
                    origin_header=origin,
                    extra={
                        "existing_price": existing[0].get("EC最安値", 0),
                        "existing_source": existing[0].get("ECソース", ""),
                        "product_name": str(row["商品名"])[:60],
                    },
                )
                self._respond(200, {"action": "skipped", "reason": "existing price is lower", **new_item})
                return

            # より安い価格を見つけた場合、既存の enrichment field を保護して
            # 価格関連フィールドのみ更新する（auto_extract がセットした
            # backup_shops / 推奨売却先 / メルカリ想定売値 / カード還元 等を失わない）
            if existing:
                merged = dict(existing[0])  # 既存をベースに
                merged.update(new_item)     # new_item の価格関連フィールドで上書き
                # 価格に依存する enrichment を再計算（存在する場合のみ）
                _recalc_enrichment(merged, price, kaitori, source, pts, row.get("カテゴリ", ""))
                log.info("価格更新: JAN %s %s円→%s円 (差額 -%s円) ソース=%s→%s",
                         jan, f"{existing[0]['EC最安値']:,}", f"{price:,}",
                         f"{existing[0]['EC最安値'] - price:,}",
                         existing[0].get("ECソース", "?"), source)
            else:
                merged = new_item

            # 同一JAN削除 → 追加
            results = [r for r in results if r.get("JAN") != jan]
            results.append(merged)
            # ロック内書き込み（_save_cache が再度ロック取得するが filelock は再帰可）
            tmp = CACHE_FILE.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(results, ensure_ascii=False, indent=2, default=_default_json),
                encoding="utf-8",
            )
            tmp.replace(CACHE_FILE)

            # POST履歴: 追加 or 更新
            _log_post_event(
                jan=jan, price=price, source=source, shop=shop, url=url,
                action="updated" if existing else "added",
                reason="cheaper than existing" if existing else "new entry",
                origin_header=origin,
                extra={
                    "kaitori": int(kaitori),
                    "profit": merged.get("現金利益", 0),
                    "product_name": str(row["商品名"])[:60],
                    "previous_price": existing[0].get("EC最安値", 0) if existing else None,
                },
            )

        log.info("追加: JAN %s %s円 [%s] 利益%s円 PT込%s円 %s",
                 jan, f"{price:,}", source,
                 f"{profit_info['cash_profit']:+,}", f"{profit_info['profit_with_points']:+,}",
                 row["商品名"][:30])

        self._respond(200, {"action": "added", **new_item})

    def _respond(self, code: int, data: dict):
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(
                json.dumps(data, ensure_ascii=False, default=_default_json).encode("utf-8")
            )
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # クライアントが応答待ち途中で切断した場合はサイレントに無視
            # （auto_extract.py のタイムアウトや Chrome拡張のタブ閉じ時に発生する）
            pass

    def handle_one_request(self):
        """接続切断を上位でもキャッチして例外トレースバックを抑制"""
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

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

    def _handle_profit_check(self):
        """JANが利益商品候補か問い合わせる（Chrome拡張の即購入バナー用）

        GET /profit_check?jan=4549292167382
        → {"is_profit": true, "profit": 12000, "price": 95980,
           "name": "...", "ec_source": "楽天", "buyback_shop": "ルデヤ"}
        または
        → {"is_profit": false}
        """
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        jan = (qs.get("jan", [""])[0] or "").strip()
        if not jan:
            self._respond(400, {"error": "jan required"})
            return

        # cache_results から該当JANの利益情報を探す
        cache = _load_cache()
        for r in cache:
            if not isinstance(r, dict):
                continue
            if r.get("JAN") != jan:
                continue
            profit = r.get("現金利益", 0)
            if profit <= 0:
                continue
            self._respond(200, {
                "is_profit": True,
                "jan": jan,
                "profit": int(profit),
                "price": int(r.get("EC最安値", 0) or 0),
                "name": r.get("商品名", ""),
                "ec_source": r.get("ECソース", ""),
                "buyback_shop": r.get("買取店", ""),
                "ec_url": r.get("EC URL", ""),
                "buyback_url": r.get("買取確認", ""),
                "stock_status": r.get("在庫状況", ""),
            })
            return
        self._respond(200, {"is_profit": False})

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

    # API トークン初期化（file 読み込み or 新規生成）
    global _API_TOKEN
    _API_TOKEN = _get_or_create_api_token()

    server = HTTPServer(("127.0.0.1", args.port), PriceHandler)
    log.info("価格収集サーバー起動: http://127.0.0.1:%d", args.port)
    log.info("POST /add_price — Chrome拡張から価格を受信")
    log.info("GET  /status    — サーバー状態確認")
    log.info("認証: X-Kaitori-Token ヘッダ必須（127.0.0.1 からはstrict=Offならスキップ可）")
    log.info("Ctrl+C で停止")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("サーバー停止")
        server.server_close()


if __name__ == "__main__":
    main()
