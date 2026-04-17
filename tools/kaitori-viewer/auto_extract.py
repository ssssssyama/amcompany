"""バックグラウンド利益商品自動抽出CLI

使い方:
    python auto_extract.py
    python auto_extract.py --threshold 5000 --shipping 1500
    python auto_extract.py --top 100 --shops 商店 森森 ルデヤ
    python auto_extract.py --rakuten-bonus 10 --yahoo-bonus 7
"""

import argparse
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from csv_loader import SHOP_NAMES, is_excluded, load_csv
from ec_search import batch_search_ec_prices
from profit import calculate_cash_profit, is_above_threshold

_LOCAL_DATA_DIR = Path.home() / ".kaitori-viewer"
_LOCAL_DATA_DIR.mkdir(exist_ok=True)
CACHE_FILE = _LOCAL_DATA_DIR / "cache_results.json"
LOG_DIR = _LOCAL_DATA_DIR / "logs"

# 量販店ECの検索URLテンプレート（{JAN}がJANコードに置換される）
EC_SEARCH_URLS = {
    "価格.com": "https://search.kakaku.com/{JAN}/",
    "Amazon": "https://www.amazon.co.jp/s?k={JAN}",
    "ヨドバシ": "https://www.yodobashi.com/?word={JAN}",
    "ビックカメラ": "https://www.biccamera.com/bc/category/?q={JAN}",
    "ケーズデンキ": "https://www.ksdenki.com/shop/e/search/?keyword={JAN}",
    "ジョーシン": "https://joshinweb.jp/servlet/emall/search?keyword={JAN}",
    "ノジマ": "https://online.nojima.co.jp/app/catalog/list/init?searchWord={JAN}",
    "エディオン": "https://www.edion.com/item_list.html?keyword={JAN}",
    "ソフマップ": "https://www.sofmap.com/search_result.aspx?keyword={JAN}",
    "コジマ": "https://www.kojima.net/ec/disp/CSfDispListPage_001.jsp?keyword={JAN}",
    "Qoo10": "https://www.qoo10.jp/s/{JAN}?keyword={JAN}",
    "auPAYマーケット": "https://wowma.jp/itemlist?e_scope=O&keyword={JAN}",
}
CSV_DIR = Path(__file__).resolve().parent.parent.parent


def load_cache() -> list:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_cache(data: list):
    try:
        tmp = CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(CACHE_FILE)
    except OSError as e:
        logging.getLogger(__name__).warning("キャッシュ保存失敗（ディスク容量不足？）: %s", e)


def bonus_points(ec_price: int, source: str, rakuten_rate: float, yahoo_rate: float) -> int:
    rates = {"楽天": rakuten_rate, "Yahoo": yahoo_rate}
    rate = rates.get(source, 0.0)
    return int(ec_price * rate / 100)


def _setup_logging():
    """コンソール + ファイルのログ設定"""
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    return log_file


PRICE_SERVER_URL = "http://127.0.0.1:8502"


def _post_crawl_queue(jan_list: list[str], sites: list[str], log) -> bool:
    """price_server のクロールキューにJANを投入する。

    Chrome拡張の background.js が自動ポーリングで検知し巡回を開始する。

    Returns:
        True: 投入成功
        False: price_server 未起動等で失敗
    """
    import urllib.request

    payload = json.dumps({"janList": jan_list, "sites": sites}).encode("utf-8")
    req = urllib.request.Request(
        f"{PRICE_SERVER_URL}/crawl_queue",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            log.info("[巡回] クロールキュー投入: %d件追加 (キュー合計%d件)",
                     result.get("added", 0), result.get("queued", 0))
            log.info("[巡回] Chrome拡張が5秒以内に自動ポーリングで巡回を開始します")
            return True
    except Exception as e:
        log.warning("[巡回] クロールキュー投入失敗: %s", e)
        return False


def _queue_extension_crawl(jan_list: list[str], ec_map: dict, log):
    """全JANをChrome拡張の巡回キューに投入する。

    API/スクレイパーで結果が取れたJANでも、ブロック済みサイト（ビックカメラ等）に
    より安い価格がある可能性があるため、全件を巡回対象にする。

    price_server が起動中なら POST /crawl_queue で投入。
    Chrome拡張の background.js が自動ポーリングで巡回を開始する。
    price_server が未起動の場合は何もしない（サイレント）。
    """
    from retailers import EXTENSION_ONLY_RETAILERS

    if not jan_list:
        return

    sites = EXTENSION_ONLY_RETAILERS
    if _post_crawl_queue(jan_list, sites, log):
        log.info("[拡張巡回] %d件のJANをChrome拡張の巡回キューに投入しました（%sサイト対象）",
                 len(jan_list), len(sites))


def _wait_crawl_completion(jan_list: list[str], sites: list[str], log, timeout: int = 600):
    """Chrome拡張の巡回完了を待つ。

    キャッシュに結果が蓄積されるのを監視して進捗を表示する。
    """
    import urllib.request

    total_expected = len(jan_list) * len(sites)
    start_cache_count = len(load_cache())
    start_time = time.time()

    log.info("[巡回] 待機中... (最大%d秒、Chrome拡張が%d件のURLを巡回予定)",
             timeout, total_expected)

    server_failures = 0
    while time.time() - start_time < timeout:
        time.sleep(10)

        current_cache = load_cache()
        new_results = len(current_cache) - start_cache_count
        elapsed = int(time.time() - start_time)

        # price_server のステータスを確認
        try:
            req = urllib.request.Request(f"{PRICE_SERVER_URL}/status")
            with urllib.request.urlopen(req, timeout=3) as resp:
                status = json.loads(resp.read())
                cache_count = status.get("cache_count", 0)
            server_failures = 0
        except Exception:
            cache_count = len(current_cache)
            server_failures += 1
            if server_failures >= 3:
                log.warning("[巡回] price_server に接続できません。巡回待機を終了します。")
                break

        log.info("[巡回] %d秒経過: 新規結果 +%d件 (キャッシュ合計%d件)",
                 elapsed, new_results, cache_count)

        # 全JAN がキャッシュに載ったら完了
        cached_jans = {r.get("JAN") for r in current_cache}
        remaining = [j for j in jan_list if j not in cached_jans]
        if not remaining:
            log.info("[巡回] 全JAN の結果を受信完了")
            break

    elapsed = int(time.time() - start_time)
    final_cache = load_cache()
    new_total = len(final_cache) - start_cache_count
    log.info("[巡回] 巡回完了: %d秒, 新規結果 +%d件", elapsed, new_total)


def main():
    parser = argparse.ArgumentParser(description="利益商品自動抽出")
    parser.add_argument("--csv", type=str, default="", help="CSVファイルパス（省略時は最新）")
    parser.add_argument("--threshold", type=int, default=1000, help="最低利益閾値(円)")
    parser.add_argument("--shipping", type=int, default=1000, help="送料合計(円)")
    parser.add_argument("--top", type=int, default=200, help="検索件数（利益候補スコア上位N件）")
    parser.add_argument("--shops", nargs="*", default=None, help="利用する買取店（省略時は全店）")
    parser.add_argument("--rakuten-bonus", type=float, default=None, help="楽天ボーナスPT(%%)。省略時はキャンペーンカレンダーから自動算出")
    parser.add_argument("--yahoo-bonus", type=float, default=None, help="Yahoo!ボーナスPT(%%)。省略時はキャンペーンカレンダーから自動算出")
    parser.add_argument("--pt-threshold", type=int, default=0, help="PT込利益の閾値(円)。指定時はPT込利益で判定")
    parser.add_argument("--min-kaitori", type=int, default=5000, help="買取価格の下限(円)。これ未満の商品はスキップ")
    parser.add_argument("--no-scraper", action="store_true", help="スクレイパー(Amazon/ヨドバシ)を無効化。API(楽天/Yahoo)のみで高速検索")
    parser.add_argument("--open-browser", type=int, default=0, metavar="N",
                        help="利益上位N件の量販店検索URLをブラウザで開く（例: --open-browser 5）")
    parser.add_argument("--ec-sites", nargs="*", default=list(EC_SEARCH_URLS.keys()),
                        help=f"ブラウザで開くECサイト（デフォルト: 全サイト）。選択肢: {', '.join(EC_SEARCH_URLS.keys())}")
    parser.add_argument("--clear-cache", action="store_true", help="キャッシュをクリアしてから実行")
    parser.add_argument("--categories", nargs="*",
                        default=["カメラ", "レンズ", "デジタル一眼", "デジカメ", "ビデオカメラ",
                                 "ゲーム", "ゲーム機", "Nintendo Switch", "プレイステーション",
                                 "グラフィックボード"],
                        help="検索対象カテゴリキーワード（カテゴリ名に含まれていればマッチ）。"
                             "--categories all で全カテゴリ対象")
    parser.add_argument("--browse", type=int, default=0, metavar="N",
                        help="買取候補スコア上位N件をブラウザで開いて目視確認（EC検索不要）")
    parser.add_argument("--crawl", type=int, default=0, metavar="N",
                        help="Chrome拡張巡回モード: 上位N件の量販店ページを実ブラウザで順番に開き価格を自動収集")
    args = parser.parse_args()

    # キャンペーンカレンダーでボーナス率を自動算出（手動指定がない場合）
    from campaign_calendar import get_bonus_rates, get_active_campaigns

    if args.rakuten_bonus is None or args.yahoo_bonus is None:
        rates = get_bonus_rates()
        if args.rakuten_bonus is None:
            args.rakuten_bonus = rates["rakuten"]
        if args.yahoo_bonus is None:
            args.yahoo_bonus = rates["yahoo"]

    log = logging.getLogger(__name__)
    log_file = _setup_logging()

    # --crawl: Chrome拡張巡回 + API/スクレイパー並行実行モード
    if args.crawl > 0:
        import threading
        import webbrowser as _wb

        # CSV読み込み
        if args.csv:
            csv_path = Path(args.csv)
        else:
            csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
            if not csv_files:
                log.error("CSVファイルが見つかりません。")
                sys.exit(1)
            csv_path = csv_files[0]

        df = load_csv(str(csv_path))

        # 買取店フィルタ
        selected_shops = args.shops if args.shops is not None else list(SHOP_NAMES)
        if set(selected_shops) != set(SHOP_NAMES):
            shop_price_cols = [f"{s}_価格" for s in selected_shops if f"{s}_価格" in df.columns]
            if shop_price_cols:
                df["最高買取価格"] = df[shop_price_cols].max(axis=1)
                df = df[df["最高買取価格"] > 0]

        # フィルタ
        df = df[df["最高買取価格"] >= args.min_kaitori]
        df = df[~df.apply(lambda r: is_excluded(r["商品名"], r.get("カテゴリ", "")), axis=1)]

        # カテゴリフィルタ
        if args.categories and args.categories != ["all"]:
            df = df[df["カテゴリ"].apply(
                lambda c: any(kw in str(c) for kw in args.categories) if c else False
            )]

        sort_key = "利益候補スコア" if "利益候補スコア" in df.columns else "最高買取価格"
        targets = df.sort_values(sort_key, ascending=False).head(args.crawl)
        target_rows = {row["JAN"]: row for _, row in targets.iterrows()}
        jan_list = list(target_rows.keys())

        # 既にキャッシュ済みのJANを除外（巡回用）
        cached = {r["JAN"] for r in load_cache() if "JAN" in r}
        uncached_jans = [j for j in jan_list if j not in cached]

        CRAWL_SITES = {
            "ビックカメラ": "https://www.biccamera.com/bc/category/?q={JAN}",
            "ケーズデンキ": "https://www.ksdenki.com/shop/e/search/?keyword={JAN}",
            "ジョーシン": "https://joshinweb.jp/servlet/emall/search?keyword={JAN}",
            "ノジマ": "https://online.nojima.co.jp/app/catalog/list/init?searchWord={JAN}",
            "エディオン": "https://www.edion.com/item_list.html?keyword={JAN}",
            "ソフマップ": "https://www.sofmap.com/search_result.aspx?keyword={JAN}",
            "コジマ": "https://www.kojima.net/ec/disp/CSfDispListPage_001.jsp?keyword={JAN}",
            "Qoo10": "https://www.qoo10.jp/s/{JAN}?keyword={JAN}",
            "auPAYマーケット": "https://wowma.jp/itemlist?e_scope=O&keyword={JAN}",
        }

        sites = [s for s in args.ec_sites if s in CRAWL_SITES] if args.ec_sites else list(CRAWL_SITES.keys())

        log.info("=== 並行検索 + Chrome拡張巡回モード ===")
        log.info("CSV: %s (%s件中 上位%s件)", csv_path.name, f"{len(df):,}", args.crawl)
        log.info("楽天/Yahoo API + スクレイパー（Amazon/ヨドバシ/価格.com）: バックグラウンド実行")
        log.info("Chrome拡張巡回（%s）: %s件", ", ".join(sites), len(uncached_jans))
        log.info("")

        # === バックグラウンド: 楽天/Yahoo API + スクレイパー ===
        api_results = []  # バックグラウンドスレッドの結果
        api_done = threading.Event()

        def _run_api_search():
            """楽天/Yahoo API + Amazon/ヨドバシ/価格.com スクレイパーを実行"""
            name_map = {jan: target_rows[jan]["商品名"] for jan in jan_list}
            price_map = {jan: int(target_rows[jan]["最高買取価格"]) for jan in jan_list}

            log.info("[API] 楽天/Yahoo + スクレイパー 検索開始 (%s件, 2並列)", len(jan_list))

            def _on_result(jan, ec):
                if not ec:
                    return
                # 在庫切れでも利益商品は入荷待ちとしてキャッシュに残す
                row = target_rows[jan]
                kaitori = int(row["最高買取価格"])
                pts = ec["points"] + bonus_points(ec["price"], ec["source"], args.rakuten_bonus, args.yahoo_bonus)
                profit_info = calculate_cash_profit(kaitori, ec["price"], args.shipping, pts)

                if not is_above_threshold(kaitori, ec["price"], args.threshold, args.shipping):
                    return

                item = {
                    "JAN": jan, "商品名": row["商品名"],
                    "最高買取価格": kaitori, "買取店": row["最高値店舗"],
                    "買取確認": row.get("買取確認", ""),
                    "EC最安値": ec["price"], "EC店舗": ec["shop"],
                    "ECソース": ec["source"], "EC URL": ec["url"],
                    "ポイント": pts, "送料": args.shipping,
                    "現金利益": profit_info["cash_profit"],
                    "PT込利益": profit_info["profit_with_points"],
                    "ROI(%)": profit_info["roi"],
                    "stock_status": ec.get("stock_status", "unknown"),
                    "在庫状況": {
                        "in_stock": "在庫あり", "limited": "残りわずか",
                        "out_of_stock": "在庫なし",
                    }.get(ec.get("stock_status", ""), "未確認"),
                    "商品リンク": ec["url"],
                    "取得日時": datetime.now().strftime("%m/%d %H:%M"),
                }
                api_results.append(item)
                log.info("[API] 利益発見: %s円 (PT込%s円) [%s] %s",
                         f"{profit_info['cash_profit']:+,}", f"{profit_info['profit_with_points']:+,}",
                         ec["source"], row["商品名"][:35])

            batch_search_ec_prices(
                jan_list,
                on_result=_on_result,
                product_names=name_map,
                kaitori_prices=price_map,
                threshold=args.threshold,
                shipping_cost=args.shipping,
                include_retailers=not args.no_scraper,
            )
            log.info("[API] 検索完了: %s件の利益商品を発見", len(api_results))
            api_done.set()

        api_thread = threading.Thread(target=_run_api_search, daemon=True)
        api_thread.start()

        # === メインスレッド: Chrome拡張巡回 ===
        if uncached_jans:
            log.info("[巡回] Chrome拡張巡回開始 (%s件 × %sサイト)", len(uncached_jans), len(sites))
            log.info("[巡回] Chrome拡張「買取価格コレクター」+ price_server が必要です")

            # price_server のクロールキューに投入 → Chrome拡張が自動ポーリングで巡回開始
            _crawl_queued = _post_crawl_queue(uncached_jans, sites, log)

            if _crawl_queued:
                # Chrome拡張の巡回完了を待つ（ポーリング）
                _wait_crawl_completion(uncached_jans, sites, log, timeout=600)
            else:
                # price_server 未起動の場合はフォールバック: 従来の webbrowser.open()
                log.warning("[巡回] price_server に接続できません。従来モードで巡回します。")
                import webbrowser as _wb
                total_urls = len(uncached_jans) * len(sites)
                opened = 0
                for jan in uncached_jans:
                    for site_name in sites:
                        url = CRAWL_SITES[site_name].replace("{JAN}", jan)
                        opened += 1
                        log.info("[巡回 %d/%d] %s %s", opened, total_urls, site_name, jan)
                        _wb.open(url)
                        time.sleep(random.uniform(5.0, 8.0))
                log.info("[巡回] 完了: %d件のURLを開きました", total_urls)
        else:
            log.info("[巡回] 全てキャッシュ済みのためスキップ")

        # === API検索の完了を待つ ===
        if not api_done.is_set():
            log.info("[待機] API検索の完了を待っています...")
            api_done.wait(timeout=300)

        # === 結果統合 ===
        # API結果をキャッシュに追加（Chrome拡張の結果は price_server 側で既に保存済み）
        all_results = list(load_cache())  # Chrome拡張巡回で蓄積された結果
        existing_jans = {r.get("JAN") for r in all_results}
        for item in api_results:
            if item["JAN"] not in existing_jans:
                all_results.append(item)
                existing_jans.add(item["JAN"])
            else:
                # 既存の結果よりAPI結果のほうが安ければ上書き
                for i, existing in enumerate(all_results):
                    if existing.get("JAN") == item["JAN"] and item.get("EC最安値", 0) < existing.get("EC最安値", float("inf")):
                        all_results[i] = item
                        break
        save_cache(all_results)

        # === サマリー表示 ===
        profitable = [r for r in all_results if r.get("現金利益", 0) > 0]
        log.info("=" * 60)
        log.info("=== 完了 ===")
        log.info("API/スクレイパー利益商品: %s件", len(api_results))
        log.info("合計利益商品（Chrome拡張含む）: %s件", len(profitable))
        if profitable:
            sorted_p = sorted(profitable, key=lambda x: x.get("PT込利益", 0), reverse=True)
            for r in sorted_p[:20]:
                log.info("  %+8s円 (PT込%+8s円) 買取%8s円 EC%8s円 [%s] %s",
                         f"{r['現金利益']:,}", f"{r['PT込利益']:,}",
                         f"{r['最高買取価格']:,}", f"{r['EC最安値']:,}",
                         r.get("ECソース", "拡張"), r["商品名"][:35])
            if len(sorted_p) > 20:
                log.info("  ... 他%s件", len(sorted_p) - 20)
        log.info("結果: %s", CACHE_FILE)
        log.info("ログ: %s", log_file)
        sys.exit(0)

    # --browse: CSVの買取候補上位をブラウザで巡回し価格を自動取得
    if args.browse > 0:
        import re as _re

        # CSV読み込み
        if args.csv:
            csv_path = Path(args.csv)
        else:
            csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
            if not csv_files:
                log.error("CSVファイルが見つかりません。")
                sys.exit(1)
            csv_path = csv_files[0]

        df = load_csv(str(csv_path))

        # 買取店フィルタ
        selected_shops = args.shops if args.shops is not None else list(SHOP_NAMES)
        if set(selected_shops) != set(SHOP_NAMES):
            shop_price_cols = [f"{s}_価格" for s in selected_shops if f"{s}_価格" in df.columns]
            if shop_price_cols:
                df["最高買取価格"] = df[shop_price_cols].max(axis=1)
                df = df[df["最高買取価格"] > 0]

        # フィルタ
        df = df[df["最高買取価格"] >= args.min_kaitori]
        df = df[~df.apply(lambda r: is_excluded(r["商品名"], r.get("カテゴリ", "")), axis=1)]

        # ソート
        sort_key = "利益候補スコア" if "利益候補スコア" in df.columns else "最高買取価格"
        targets = df.sort_values(sort_key, ascending=False).head(args.browse)

        sites = [s for s in args.ec_sites if s in EC_SEARCH_URLS]
        _PAGE_TIMEOUT = 6000  # ページ読み込みタイムアウト(ms)

        log.info("=== ブラウザ巡回モード ===")
        log.info("CSV: %s (%s件中 上位%s件)", csv_path.name, f"{len(df):,}", len(targets))
        log.info("ECサイト: %s", ", ".join(sites))

        found_items = []

        try:
            from playwright.sync_api import sync_playwright

            from stealth import create_stealth_context

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=False, timeout=15000)
                try:
                    context = create_stealth_context(browser, viewport={"width": 1400, "height": 900})

                    for i, (_, row) in enumerate(targets.iterrows()):
                        jan = row["JAN"]
                        name = row["商品名"][:35]
                        kaitori = int(row["最高買取価格"])
                        shop = row["最高値店舗"]
                        log.info("[%d/%d] %s 買取%s円(%s) %s", i + 1, len(targets), jan, f"{kaitori:,}", shop, name)

                        best_price = None
                        best_site = ""

                        for site_name in sites:
                            url = EC_SEARCH_URLS[site_name].replace("{JAN}", jan)
                            page = context.new_page()
                            try:
                                page.goto(url, timeout=_PAGE_TIMEOUT, wait_until="domcontentloaded")
                                time.sleep(random.uniform(0.8, 2.0))

                                # 汎用価格抽出: ￥付き価格を探す
                                text = page.text_content("body") or ""
                                yen_matches = _re.findall(r"[￥¥](\d{1,3}(?:,\d{3})+)", text)
                                prices = [v for v in (int(m.replace(",", "")) for m in yen_matches) if v >= 1000]

                                if prices:
                                    price = min(prices)
                                    profit = kaitori - price - args.shipping
                                    mark = "◎" if profit >= args.threshold else "△" if profit > 0 else "✗"
                                    log.info("  %s %s: %s円 (利益%s円)", mark, site_name, f"{price:,}", f"{profit:+,}")

                                    if best_price is None or price < best_price:
                                        best_price = price
                                        best_site = site_name
                                else:
                                    log.info("  - %s: 価格なし", site_name)

                            except Exception as e:
                                log.info("  - %s: %s", site_name, e)
                            finally:
                                page.close()

                        if best_price is not None:
                            profit = kaitori - best_price - args.shipping
                            if profit >= args.threshold:
                                found_items.append({
                                    "JAN": jan, "商品名": row["商品名"],
                                    "最高買取価格": kaitori, "買取店": shop,
                                    "EC最安値": best_price, "ECサイト": best_site,
                                    "利益": profit,
                                })
                finally:
                    browser.close()

        except ImportError:
            log.error("Playwright がインストールされていません。pip install playwright && playwright install")
            sys.exit(1)

        # 結果サマリー
        log.info("=" * 60)
        if found_items:
            log.info("利益商品: %s件（閾値%s円以上）", len(found_items), f"{args.threshold:,}")
            for item in sorted(found_items, key=lambda x: x["利益"], reverse=True):
                log.info(
                    "  %+8s円 買取%8s円 EC%8s円 [%s] %s",
                    f"{item['利益']:,}", f"{item['最高買取価格']:,}",
                    f"{item['EC最安値']:,}", item["ECサイト"], item["商品名"][:35],
                )
        else:
            log.info("利益商品なし")
        log.info("=== 完了 ===")
        sys.exit(0)

    # CSV読み込み
    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
        if not csv_files:
            log.error("CSVファイルが見つかりません。")
            sys.exit(1)
        csv_path = csv_files[0]

    log.info("=== 利益商品自動抽出 開始 ===")
    log.info("ログファイル: %s", log_file)
    log.info("CSV: %s", csv_path.name)
    df = load_csv(str(csv_path))
    log.info("総商品数: %s", f"{len(df):,}")

    # 買取店フィルタ
    selected_shops = args.shops if args.shops is not None else list(SHOP_NAMES)
    if set(selected_shops) != set(SHOP_NAMES):
        shop_price_cols = [f"{s}_価格" for s in selected_shops if f"{s}_価格" in df.columns]
        if shop_price_cols:
            df["最高買取価格"] = df[shop_price_cols].max(axis=1)
            def best_shop(row):
                best_p, best_s = 0, ""
                for s in selected_shops:
                    col = f"{s}_価格"
                    if col in row.index and row[col] > best_p:
                        best_p = row[col]
                        best_s = s
                return best_s
            df["最高値店舗"] = df.apply(best_shop, axis=1)
            df = df[df["最高買取価格"] > 0]
    log.info("対象買取店: %s", ", ".join(selected_shops))

    # 買取価格下限フィルタ
    before_count = len(df)
    df = df[df["最高買取価格"] >= args.min_kaitori]
    skipped = before_count - len(df)
    if skipped > 0:
        log.info("買取価格 %s円未満をスキップ: %s件除外", f"{args.min_kaitori:,}", f"{skipped:,}")

    # 除外フィルタ（iPhone・中古・破損等）
    before_exclude = len(df)
    df = df[~df.apply(lambda r: is_excluded(r["商品名"], r.get("カテゴリ", "")), axis=1)]
    excluded = before_exclude - len(df)
    if excluded > 0:
        log.info("除外フィルタ: %s件除外（iPhone・中古・破損等）", f"{excluded:,}")

    # カテゴリフィルタ
    if args.categories and args.categories != ["all"]:
        before_cat = len(df)
        cat_keywords = args.categories

        def _matches_category(cat_str):
            cat_str = str(cat_str) if cat_str else ""
            return any(kw in cat_str for kw in cat_keywords)

        df = df[df["カテゴリ"].apply(_matches_category)]
        cat_filtered = before_cat - len(df)
        if cat_filtered > 0:
            log.info("カテゴリフィルタ: %s件除外 → %s件残（%s）",
                     f"{cat_filtered:,}", f"{len(df):,}", ", ".join(cat_keywords))
    else:
        log.info("カテゴリ: 全カテゴリ対象")

    # ソート
    sort_key = "利益候補スコア" if "利益候補スコア" in df.columns else "最高買取価格"
    targets = df.sort_values(sort_key, ascending=False).head(args.top)
    target_rows = {row["JAN"]: row for _, row in targets.iterrows()}
    jan_list = list(target_rows.keys())
    log.info("検索対象: %s件（%s上位）", len(jan_list), sort_key)
    log.info("現金利益閾値: %s円 / 送料: %s円", f"{args.threshold:,}", f"{args.shipping:,}")
    if args.pt_threshold > 0:
        log.info("PT込利益閾値: %s円", f"{args.pt_threshold:,}")
    log.info("楽天ボーナス: %s%% / Yahoo!ボーナス: %s%%", args.rakuten_bonus, args.yahoo_bonus)
    campaigns = get_active_campaigns()
    if campaigns:
        log.info("本日のキャンペーン: %s", ", ".join(campaigns))

    # キャッシュ
    if args.clear_cache:
        save_cache([])
        from ec_search import clear_ec_cache
        clear_ec_cache()
        log.info("キャッシュをクリアしました（利益結果 + EC検索）")

    cached = {r["JAN"]: r for r in load_cache() if "JAN" in r}
    cached_jans = [j for j in jan_list if j in cached]
    uncached_jans = [j for j in jan_list if j not in cached]
    log.info("キャッシュ済み: %s件 / 新規検索: %s件", len(cached_jans), len(uncached_jans))

    # 結果リスト（キャッシュ分を先に追加）
    results = [cached[j] for j in cached_jans]
    _browser_opened = [0]

    # バッチ検索
    if uncached_jans:
        name_map = {jan: target_rows[jan]["商品名"] for jan in uncached_jans}
        price_map = {jan: int(target_rows[jan]["最高買取価格"]) for jan in uncached_jans}

        # Chrome拡張の自動巡回キューに即座に投入（API検索と並行して巡回開始）
        _queue_extension_crawl(uncached_jans, {}, log)

        start = time.time()
        mode = "APIのみ" if args.no_scraper else "API+スクレイパー"
        log.info("検索開始（2並列, %s）...", mode)

        # PT込閾値使用時はプリフィルタを緩くする（ポイント分を考慮）
        search_threshold = 0 if args.pt_threshold > 0 else args.threshold

        # ブラウザ即時オープン用
        _open_browser_limit = args.open_browser
        if _open_browser_limit > 0:
            import webbrowser as _wb
            _browser_sites = [s for s in args.ec_sites if s in EC_SEARCH_URLS]

        # 1件完了ごとに利益判定+キャッシュ保存+ブラウザオープン
        def _on_result(jan, ec):
            if not ec:
                return
            # 在庫切れでも利益商品は入荷待ちとしてキャッシュに残す
            row = target_rows[jan]
            kaitori = int(row["最高買取価格"])
            pts = ec["points"] + bonus_points(ec["price"], ec["source"], args.rakuten_bonus, args.yahoo_bonus)
            coupon = ec.get("coupon", 0)
            # 送料無料商品はEC送料を0として扱う（買取発送料のみ）
            shipping = args.shipping
            if ec.get("free_shipping"):
                shipping = max(shipping - 500, 0)  # EC送料分を差し引く（概算500円）
            profit_info = calculate_cash_profit(kaitori, ec["price"], shipping, pts, coupon)

            if args.pt_threshold > 0:
                if profit_info["profit_with_points"] < args.pt_threshold:
                    return
            else:
                if not is_above_threshold(kaitori, ec["price"], args.threshold, shipping, coupon):
                    return

            stock = ec.get("stock_status", "unknown")
            results.append({
                "JAN": jan,
                "商品名": row["商品名"],
                "最高買取価格": kaitori,
                "買取店": row["最高値店舗"],
                "買取確認": row.get("買取確認", ""),
                "EC最安値": ec["price"],
                "EC店舗": ec["shop"],
                "ECソース": ec["source"],
                "EC URL": ec["url"],
                "ポイント": pts,
                "クーポン": coupon,
                "送料": shipping,
                "送料無料": ec.get("free_shipping", False),
                "現金利益": profit_info["cash_profit"],
                "PT込利益": profit_info["profit_with_points"],
                "ROI(%)": profit_info["roi"],
                "stock_status": stock,
                "在庫状況": {
                    "in_stock": "在庫あり",
                    "limited": "残りわずか",
                    "out_of_stock": "在庫なし",
                }.get(stock, "未確認"),
                "商品リンク": ec["url"],
                "取得日時": datetime.now().strftime("%m/%d %H:%M"),
            })
            save_cache(results)
            log.info(
                "利益発見: %s円 (PT込%s円) 買取%s円 EC%s円 [%s] %s",
                f"{profit_info['cash_profit']:+,}", f"{profit_info['profit_with_points']:+,}",
                f"{kaitori:,}", f"{ec['price']:,}", ec["source"], row["商品名"][:35],
            )

            # 利益発見時に即座に確認済みEC URLだけをブラウザで開く
            if _open_browser_limit > 0 and _browser_opened[0] < _open_browser_limit:
                ec_url = ec.get("url", "")
                if ec_url:
                    _browser_opened[0] += 1
                    _wb.open(ec_url)
                    log.info("  → ブラウザで開きました [%d/%d] %s", _browser_opened[0], _open_browser_limit, ec["source"])

        ec_map = batch_search_ec_prices(
            uncached_jans,
            on_result=_on_result,
            product_names=name_map,
            kaitori_prices=price_map,
            threshold=search_threshold,
            shipping_cost=args.shipping,
            include_retailers=not args.no_scraper,
        )

        elapsed = time.time() - start
        found = sum(1 for v in ec_map.values() if v is not None)
        log.info("検索完了: %s秒 (%s/%s件 EC価格取得)", f"{elapsed:.0f}", found, len(uncached_jans))

    # キャッシュ保存
    save_cache(results)

    # 結果表示
    all_profitable = [r for r in results if r.get("現金利益", 0) > 0]

    log.info("=" * 60)
    log.info("利益商品: %s件", len(all_profitable))
    if all_profitable:
        sorted_results = sorted(all_profitable, key=lambda x: x.get("PT込利益", 0), reverse=True)
        for r in sorted_results[:20]:
            log.info(
                "  %+8s円 (PT込%+8s円) 買取%8s円 EC%8s円 [%s] %s",
                f"{r['現金利益']:,}", f"{r['PT込利益']:,}",
                f"{r['最高買取価格']:,}", f"{r['EC最安値']:,}",
                r["ECソース"], r["商品名"][:35],
            )
        if len(sorted_results) > 20:
            log.info("  ... 他%s件", len(sorted_results) - 20)
    # PT込黒字の表示
    pt_profitable = [r for r in results if r.get("PT込利益", 0) > 0]
    if len(pt_profitable) > len(all_profitable):
        log.info("PT込黒字: %s件（現金赤字だがポイント込みで黒字）", len(pt_profitable) - len(all_profitable))

    # ヒット率と次のアクション提案
    searched_total = len(uncached_jans) + len(cached_jans) if uncached_jans else len(cached_jans)
    hit_rate = len(all_profitable) / searched_total * 100 if searched_total > 0 else 0
    log.info("ヒット率: %s/%s件 (%.1f%%)", len(all_profitable), searched_total, hit_rate)

    if len(all_profitable) == 0:
        log.info("")
        log.info("=== 利益商品が見つからない場合の対策 ===")
        log.info("  1. 閾値を下げる: --threshold 0 --pt-threshold 2000")
        log.info("  2. 検索範囲を広げる: --top 500")
        log.info("  3. 買取価格下限を下げる: --min-kaitori 3000")
        log.info("  4. キャンペーン日に再実行: 楽天マラソン中・5のつく日はPT還元増")
        log.info("  5. 分析ツール: python analyze.py --shop-gap（価格差の大きい商品を確認）")

    log.info("結果は %s に保存済み", CACHE_FILE.name)
    log.info("ログファイル: %s", log_file)

    # ブラウザで確認済みEC URLを開く（キャッシュ済み分。検索中に見つかった分は既に開済み）
    if args.open_browser > 0 and cached_jans and all_profitable:
        import webbrowser

        already_opened = _browser_opened[0] if uncached_jans else 0
        remaining = args.open_browser - already_opened
        if remaining > 0:
            sorted_for_browser = sorted(all_profitable, key=lambda x: x.get("PT込利益", 0), reverse=True)
            cached_jan_set = set(cached_jans)
            cached_profitable = [r for r in sorted_for_browser if r["JAN"] in cached_jan_set and r.get("商品リンク")]
            open_count = min(remaining, len(cached_profitable))

            if open_count > 0:
                log.info("キャッシュ済み利益商品 %s件の確認済みEC URLを開きます...", open_count)
                for item in cached_profitable[:open_count]:
                    webbrowser.open(item["商品リンク"])
                    time.sleep(random.uniform(0.2, 0.6))

    log.info("=== 完了 ===")


if __name__ == "__main__":
    main()
