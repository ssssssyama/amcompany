"""モール横断アービトラージ（戦略F）

楽天・Yahoo!ショッピングで同一JANの価格を取得し、価格差が大きい商品を発見する。
EC→EC転売（楽天で買ってYahooで売る、またはその逆）の候補を抽出。

使い方:
    from mall_arbitrage import find_mall_gaps
    gaps = find_mall_gaps(jan_list, min_gap=2000)

    # 単体テスト
    python mall_arbitrage.py
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


def find_mall_gaps(jan_list: list[str], min_gap: int = 2000) -> list[dict]:
    """各JANで楽天とYahooの価格を取得し、価格差が大きいものを返す。

    Args:
        jan_list: 検索対象JANリスト
        min_gap: 価格差がこの円数（円）以上のものだけ返す

    Returns:
        [{jan, rakuten_price, yahoo_price, gap, buy_at, sell_at,
          rakuten_url, yahoo_url, name}, ...] 価格差降順
    """
    from ec_search import search_rakuten_by_jan, search_yahoo_by_jan

    results: list[dict] = []

    def _fetch_pair(jan: str) -> dict | None:
        try:
            r = search_rakuten_by_jan(jan)
        except Exception as e:
            logger.debug("楽天取得失敗 %s: %s", jan, e)
            r = None
        try:
            y = search_yahoo_by_jan(jan)
        except Exception as e:
            logger.debug("Yahoo取得失敗 %s: %s", jan, e)
            y = None

        if not r or not y:
            return None

        r_price = r.get("price", 0)
        y_price = y.get("price", 0)
        if r_price <= 0 or y_price <= 0:
            return None

        gap = abs(r_price - y_price)
        if gap < min_gap:
            return None

        if r_price < y_price:
            buy_at, sell_at = "楽天", "Yahoo"
        else:
            buy_at, sell_at = "Yahoo", "楽天"

        return {
            "jan": jan,
            "rakuten_price": r_price,
            "yahoo_price": y_price,
            "gap": gap,
            "buy_at": buy_at,
            "sell_at": sell_at,
            "rakuten_url": r.get("url", ""),
            "yahoo_url": y.get("url", ""),
            "name": r.get("name", "") or y.get("name", ""),
        }

    # 並列実行（API側のグローバルロックで実質直列化されるが、待ち時間は重なる）
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(_fetch_pair, jan): jan for jan in jan_list}
        for fut in as_completed(futures):
            entry = fut.result()
            if entry:
                results.append(entry)

    return sorted(results, key=lambda x: x["gap"], reverse=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from pathlib import Path
    from csv_loader import load_csv

    CSV_DIR = Path(__file__).resolve().parent.parent.parent
    csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
    if not csv_files:
        print("CSVなし")
        exit(1)

    df = load_csv(str(csv_files[0]))
    # 利益候補スコア上位30件で検証
    target_jans = df.sort_values("利益候補スコア", ascending=False).head(30)["JAN"].tolist()
    print(f"検証対象: {len(target_jans)}件のJANを楽天/Yahooで取得中...")

    gaps = find_mall_gaps(target_jans, min_gap=2000)
    print(f"\n=== モール横断アービトラージ ===")
    print(f"発見数: {len(gaps)}件")
    for g in gaps[:15]:
        print(f"  {g['jan']}: 差{g['gap']:,}円 "
              f"(楽天{g['rakuten_price']:,} vs Yahoo{g['yahoo_price']:,}) "
              f"→ {g['buy_at']}で買い → {g['sell_at']}で売り")
