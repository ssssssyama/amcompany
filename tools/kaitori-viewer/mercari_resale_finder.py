"""メルカリ転売利益候補発見（ハードオフ仕入 → メルカリ販売）

ハードオフネットモールから中古商品を仕入れ、メルカリで個人売買で売却する
無在庫転売モデル。買取店モデル（買取は新品のみ）とは別系統。

利益計算:
    メルカリ予想販売価格 = 参考買取価格 × 1.20
    メルカリ手取り = 販売価格 × 0.9（手数料10%） - 配送料
    転売利益 = メルカリ手取り - ハードオフ価格

使い方:
    from mercari_resale_finder import find_mercari_resale_candidates
    candidates = find_mercari_resale_candidates(jan_list, df)

    # 単体テスト
    python mercari_resale_finder.py --top 30
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_FILE = Path.home() / ".kaitori-viewer" / "mercari_resale_results.json"
# メルカリ販売予想価格の係数（買取価格 × MERCARI_PRICE_RATIO）
# 中古品は新品買取よりプレミアムが乗るため 1.20 で見積もり（既存 analyze.py と同係数）
MERCARI_PRICE_RATIO = 1.20
DEFAULT_SHIPPING = 800  # らくらくメルカリ便
MAX_WORKERS = 2  # ハードオフ並列取得数


def _save_cache(results: list) -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")


def find_mercari_resale_candidates(
    jan_list: list[str],
    df,
    min_profit: int = 1000,
    shipping_cost: int = DEFAULT_SHIPPING,
) -> list[dict]:
    """ハードオフ仕入 → メルカリ販売の転売利益候補を返す。

    Args:
        jan_list: 検索対象JAN
        df: csv_loader.load_csv() の戻り値（参考買取価格取得用）
        min_profit: 利益閾値（円）
        shipping_cost: メルカリ配送料（デフォルト らくらくメルカリ便800円）

    Returns:
        利益候補のdictリスト（利益降順）
    """
    from retailer_scraper import search_hardoff
    from profit import calculate_mercari_profit

    kaitori_map = {row["JAN"]: row for _, row in df.iterrows()}
    candidates: list[dict] = []

    def _check_one(jan: str) -> dict | None:
        try:
            ec = search_hardoff(jan)
        except Exception as e:
            logger.debug("ハードオフ取得失敗 %s: %s", jan, e)
            return None
        if not ec:
            return None
        if ec.get("stock_status") == "out_of_stock":
            return None

        kaitori_row = kaitori_map.get(jan)
        if kaitori_row is None:
            return None
        kaitori_price = int(kaitori_row.get("最高買取価格", 0) or 0)
        if kaitori_price <= 0:
            return None

        mercari_price = int(kaitori_price * MERCARI_PRICE_RATIO)
        profit_info = calculate_mercari_profit(
            ec_price=ec["price"],
            mercari_price=mercari_price,
            shipping_cost=shipping_cost,
        )

        if profit_info["mercari_profit"] < min_profit:
            return None

        return {
            "JAN": jan,
            "商品名": kaitori_row.get("商品名", "") or ec.get("name", ""),
            "ハードオフ仕入価格": ec["price"],
            "ハードオフURL": ec.get("url", ""),
            "中古ランク": ec.get("condition_rank") or "",
            "参考買取価格": kaitori_price,
            "メルカリ予想販売価格": mercari_price,
            "メルカリ予想手取り": profit_info["mercari_net"],
            "メルカリ予想利益": profit_info["mercari_profit"],
            "在庫状況": {
                "in_stock": "在庫あり",
                "limited": "残りわずか",
            }.get(ec.get("stock_status", ""), "未確認"),
        }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(_check_one, jan): jan for jan in jan_list}
        for fut in as_completed(futures):
            entry = fut.result()
            if entry:
                candidates.append(entry)
                logger.info("転売候補: 利益%s円 仕入%s円 %s",
                            f"{entry['メルカリ予想利益']:+,}",
                            f"{entry['ハードオフ仕入価格']:,}",
                            entry["商品名"][:30])

    candidates.sort(key=lambda x: x["メルカリ予想利益"], reverse=True)
    _save_cache(candidates)
    return candidates


if __name__ == "__main__":
    import argparse
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="メルカリ転売候補（ハードオフ仕入）")
    parser.add_argument("--top", type=int, default=20, help="CSV上位何件のJANを試すか")
    parser.add_argument("--jans", nargs="*", help="特定JANリスト")
    parser.add_argument("--min-profit", type=int, default=1000)
    args = parser.parse_args()

    from csv_loader import load_csv
    CSV_DIR = Path(__file__).resolve().parent.parent.parent
    csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
    if not csv_files:
        print("CSVなし")
        sys.exit(1)
    df = load_csv(str(csv_files[0]))

    if args.jans:
        target_jans = args.jans
    else:
        target_jans = df.sort_values("利益候補スコア", ascending=False).head(args.top)["JAN"].tolist()

    print(f"対象: {len(target_jans)}件のJANをハードオフで検索中...")
    candidates = find_mercari_resale_candidates(target_jans, df, min_profit=args.min_profit)
    print(f"\n=== メルカリ転売候補（利益≥{args.min_profit:,}円）===")
    print(f"発見: {len(candidates)}件")
    for c in candidates[:20]:
        print(f"  {c['JAN']}: 利益{c['メルカリ予想利益']:+,}円 "
              f"(仕入{c['ハードオフ仕入価格']:,}円 → メルカリ{c['メルカリ予想販売価格']:,}円) "
              f"{c['商品名'][:30]}")
