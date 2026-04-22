"""EC価格スクレイピング統合

利用可能なEC検索ソース:
  API:
    - 楽天市場 API (ec_search.py)
    - Yahoo!ショッピング API (ec_search.py)
  Playwright (retailer_scraper.py):
    - Amazon (Chromium)
    - ヨドバシ (Firefox)
    - 価格.com (Chromium)
    - Qoo10 (Chromium)
  Chrome拡張 自動巡回 (EXTENSION_ONLY_RETAILERS):
    - ビックカメラ, ジョーシン, ノジマ, ケーズデンキ, ソフマップ, エディオン, コジマ
    ※ CDP/Playwright では100%ブロックされるため Chrome拡張経由のみ
"""

RETAILER_NAMES: list[str] = [
    "Amazon", "ヨドバシ", "価格.com", "Qoo10",
    "ビックカメラ", "ジョーシン", "ノジマ", "ケーズデンキ",
    "ソフマップ", "エディオン", "コジマ",
]

# CDP接続でもブロック/SPA未描画のサイト（Chrome拡張経由のみ有効）。
# ワーカーはCDPを試行するが、サーキットブレーカー発動後はChrome拡張に依存。
# 検証結果 (2026-04-16):
#   ビックカメラ: WAF「通信に問題があるためアクセスを遮断」
#   ジョーシン: body=49（空ページ）
#   ケーズデンキ: ページ読込OK(15KB)だがSPA未描画（20秒待っても価格表示なし）
#   エディオン: goto タイムアウト
#   コジマ: goto タイムアウト
#   ソフマップ: 未検証（ビックカメラグループのため同様と推定）
#   ノジマ: ページ読込OK(227B)だが内容なし
EXTENSION_ONLY_RETAILERS = [
    "ビックカメラ",
    "ジョーシン",
    "ケーズデンキ",
    "ノジマ",
    "エディオン",
    "コジマ",
    "auPAYマーケット",  # Chrome拡張 content.js にルール追加済み、巡回キュー対象
    "セブンネット",      # 7net.omni7.jp - セブン&アイ系総合EC、ゲーム/家電
    "フジヤカメラ",      # fujiya-camera.co.jp - カメラ/レンズ専門店（新品）
    "楽天ブックス",      # books.rakuten.co.jp - 書籍/ゲーム/DVD
    # ソフマップは実ブラウザでもbot検知で「アクセス遮断」画面になるため除外
]

# 後方互換
BLOCKED_RETAILERS = EXTENSION_ONLY_RETAILERS


def search_all_retailers(
    jan: str,
    enabled: list[str] | None = None,
    progress_callback=None,
    product_name: str = "",
) -> list[dict]:
    """有効なスクレイパーで並行検索し、結果をリストで返す"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from retailer_scraper import AVAILABLE_SCRAPERS

    targets = {
        name: fn for name, fn in AVAILABLE_SCRAPERS.items()
        if enabled is None or name in enabled
    }
    if not targets:
        return []

    results = []
    # max_workers を3に制限: 11並列だと Chromium サブプロセスが同時起動し
    # Windows ページングファイルを枯渇させる (WinError 1455)
    with ThreadPoolExecutor(max_workers=min(3, len(targets))) as executor:
        futures = {
            executor.submit(fn, jan, product_name=product_name): name
            for name, fn in targets.items()
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    # 価格.comワーカーはリストを返す場合がある
                    if isinstance(result, list):
                        results.extend(result)
                    else:
                        results.append(result)
            except Exception:
                pass

    return results
