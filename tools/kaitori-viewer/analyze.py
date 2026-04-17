"""利益分析ツール

カテゴリ別分析、まとめ買い、価格トレンド、メルカリ相場比較、
ポイント再投資ROIなどの分析機能を提供する。

使い方:
    python analyze.py                    # 全分析を実行
    python analyze.py --category         # カテゴリ別利益率
    python analyze.py --bulk             # まとめ買いグルーピング
    python analyze.py --trend            # 価格トレンド（セール狙いリスト）
    python analyze.py --mercari          # メルカリ相場比較
    python analyze.py --reinvest         # ポイント再投資ROI
    python analyze.py --shop-gap         # 買取店間価格差
"""

import argparse
import json
import logging
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from csv_loader import SHOP_NAMES, load_csv
from profit import calculate_reinvest_roi, calculate_mercari_profit

_LOCAL_DATA_DIR = Path.home() / ".kaitori-viewer"
CACHE_FILE = _LOCAL_DATA_DIR / "cache_results.json"
EC_CACHE_FILE = _LOCAL_DATA_DIR / "ec_cache.json"
PRICE_HISTORY_FILE = _LOCAL_DATA_DIR / "price_history.json"
CSV_DIR = Path(__file__).resolve().parent.parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _load_cache() -> list:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _load_ec_cache() -> dict:
    if EC_CACHE_FILE.exists():
        try:
            return json.loads(EC_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _load_price_history() -> dict:
    if PRICE_HISTORY_FILE.exists():
        try:
            return json.loads(PRICE_HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_price_history(history: dict):
    try:
        tmp = PRICE_HISTORY_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
        tmp.replace(PRICE_HISTORY_FILE)
    except OSError:
        pass


# =====================================================================
# 1. カテゴリ別利益率分析
# =====================================================================

def analyze_by_category(results: list, df=None):
    """カテゴリ別の利益統計を表示する"""
    log.info("=" * 60)
    log.info("=== カテゴリ別利益率分析 ===")

    if not results:
        log.info("利益結果がありません")
        return

    # JANからカテゴリを引く
    jan_to_cat = {}
    if df is not None:
        for _, row in df.iterrows():
            jan_to_cat[row["JAN"]] = row.get("カテゴリ", "不明")

    cat_stats = defaultdict(lambda: {"count": 0, "total_profit": 0, "total_pt_profit": 0, "profits": []})
    for r in results:
        cat = jan_to_cat.get(r.get("JAN", ""), "不明") or "不明"
        # 複合カテゴリは最初のものを使用
        cat = cat.split("、")[0] if "、" in cat else cat
        profit = r.get("現金利益", 0)
        pt_profit = r.get("PT込利益", 0)
        cat_stats[cat]["count"] += 1
        cat_stats[cat]["total_profit"] += profit
        cat_stats[cat]["total_pt_profit"] += pt_profit
        cat_stats[cat]["profits"].append(profit)

    log.info("")
    log.info("%-16s %5s %10s %10s %10s", "カテゴリ", "件数", "平均利益", "最大利益", "合計PT込")
    log.info("-" * 60)

    for cat, stats in sorted(cat_stats.items(), key=lambda x: x[1]["total_pt_profit"], reverse=True):
        avg = stats["total_profit"] // stats["count"] if stats["count"] else 0
        max_p = max(stats["profits"]) if stats["profits"] else 0
        log.info("%-16s %5d %+10s %+10s %+10s",
                 cat[:16], stats["count"],
                 f"{avg:,}円", f"{max_p:,}円", f"{stats['total_pt_profit']:,}円")

    log.info("")


# =====================================================================
# 2. ポイント再投資ROI
# =====================================================================

def analyze_reinvest_roi(results: list):
    """ポイント再投資を前提としたROIを計算・表示する"""
    log.info("=" * 60)
    log.info("=== ポイント再投資ROI分析 ===")
    log.info("※ 獲得ポイントを次回仕入れに充当した場合の実質ROI")

    if not results:
        log.info("利益結果がありません")
        return

    items = []
    for r in results:
        kaitori = r.get("最高買取価格", 0)
        ec = r.get("EC最安値", 0)
        pts = r.get("ポイント", 0)
        coupon = r.get("クーポン", 0)
        shipping = r.get("送料", 0)

        if ec <= 0 or kaitori <= 0:
            continue

        reinvest = calculate_reinvest_roi(kaitori, ec, shipping, pts, coupon)
        normal_roi = r.get("ROI(%)", 0)
        items.append({
            "name": r.get("商品名", "")[:30],
            "normal_roi": normal_roi,
            "reinvest_roi": reinvest["reinvest_roi"],
            "diff": round(reinvest["reinvest_roi"] - normal_roi, 1),
            "points": pts,
        })

    items.sort(key=lambda x: x["reinvest_roi"], reverse=True)

    log.info("")
    log.info("%-32s %8s %8s %8s %8s", "商品名", "通常ROI", "再投資ROI", "差分", "PT")
    log.info("-" * 72)
    for item in items[:20]:
        log.info("%-32s %+7.1f%% %+7.1f%% %+7.1f%% %7s",
                 item["name"], item["normal_roi"], item["reinvest_roi"],
                 item["diff"], f"{item['points']:,}")

    if items:
        avg_diff = sum(i["diff"] for i in items) / len(items)
        log.info("")
        log.info("平均ROI改善: %+.1f%%ポイント（ポイント再投資効果）", avg_diff)
    log.info("")


# =====================================================================
# 3. まとめ買いグルーピング
# =====================================================================

def analyze_bulk_buy(results: list, per_item_shipping: int = 500):
    """同一EC店舗の利益商品をグルーピングし、まとめ買い候補を表示する"""
    log.info("=" * 60)
    log.info("=== まとめ買いグルーピング ===")
    log.info("※ 同一店舗からまとめ買いで送料を削減")

    if not results:
        log.info("利益結果がありません")
        return

    shop_groups = defaultdict(list)
    for r in results:
        key = (r.get("ECソース", ""), r.get("EC店舗", ""))
        if key[0] and key[1]:
            shop_groups[key].append(r)

    # 2件以上ある店舗のみ
    multi = {k: v for k, v in shop_groups.items() if len(v) >= 2}

    if not multi:
        log.info("同一店舗に2件以上の利益商品がありません")
        return

    log.info("")
    for (source, shop), items in sorted(multi.items(), key=lambda x: len(x[1]), reverse=True):
        total_profit = sum(r.get("PT込利益", 0) for r in items)
        saved = per_item_shipping * (len(items) - 1)  # 送料削減額（初回以外）
        log.info("[%s] %s — %d件 合計PT込利益%s円 送料削減%s円",
                 source, shop, len(items),
                 f"{total_profit:+,}", f"{saved:,}")
        for r in sorted(items, key=lambda x: x.get("PT込利益", 0), reverse=True):
            log.info("  %+8s円 %s %s",
                     f"{r.get('PT込利益', 0):,}",
                     f"EC{r.get('EC最安値', 0):,}円",
                     r.get("商品名", "")[:35])
        log.info("")


# =====================================================================
# 4. 価格トレンド分析
# =====================================================================

def analyze_price_trend(ec_cache: dict, results: list, df=None):
    """EC価格の履歴を記録し、価格トレンドを分析する"""
    log.info("=" * 60)
    log.info("=== 価格トレンド分析 ===")

    # 現在のec_cacheから価格履歴を更新
    history = _load_price_history()
    now = datetime.now().isoformat()
    updated = 0

    for jan, entry in ec_cache.items():
        if not isinstance(entry, dict) or entry == "__no_result__":
            continue
        price = entry.get("price", 0)
        source = entry.get("source", "")
        if price <= 0:
            continue

        if jan not in history:
            history[jan] = []
        # 同日の重複を避ける
        today = now[:10]
        if history[jan] and history[jan][-1].get("date", "")[:10] == today:
            history[jan][-1] = {"date": now, "price": price, "source": source}
        else:
            history[jan].append({"date": now, "price": price, "source": source})
        # 最大30件保持
        history[jan] = history[jan][-30:]
        updated += 1

    _save_price_history(history)
    log.info("価格履歴更新: %d件", updated)

    # 現在利益なしだが過去に安かった商品（セール狙いリスト）
    jan_to_kaitori = {}
    if df is not None:
        for _, row in df.iterrows():
            jan_to_kaitori[row["JAN"]] = {
                "kaitori": int(row["最高買取価格"]),
                "name": row["商品名"][:35],
                "shop": row["最高値店舗"],
            }

    profitable_jans = {r.get("JAN") for r in results}
    watchlist = []

    for jan, prices in history.items():
        if jan in profitable_jans or len(prices) < 2:
            continue
        info = jan_to_kaitori.get(jan)
        if not info:
            continue

        min_price = min(p["price"] for p in prices)
        current_price = prices[-1]["price"]
        kaitori = info["kaitori"]

        # 過去に利益が出る価格だったが今は出ない
        if (kaitori - min_price - 1000) >= 3000 and (kaitori - current_price - 1000) < 3000:
            watchlist.append({
                "jan": jan,
                "name": info["name"],
                "kaitori": kaitori,
                "min_price": min_price,
                "current_price": current_price,
                "potential_profit": kaitori - min_price - 1000,
            })

    if watchlist:
        watchlist.sort(key=lambda x: x["potential_profit"], reverse=True)
        log.info("")
        log.info("セール狙いリスト（過去に利益→現在は出ない商品）:")
        log.info("%-36s %8s %8s %8s %8s", "商品名", "買取", "過去最安", "現在EC", "潜在利益")
        log.info("-" * 72)
        for w in watchlist[:20]:
            log.info("%-36s %7s %7s %7s %+7s",
                     w["name"],
                     f"{w['kaitori']:,}",
                     f"{w['min_price']:,}",
                     f"{w['current_price']:,}",
                     f"{w['potential_profit']:,}")
    else:
        log.info("セール狙い対象はありません（価格履歴が少ない場合は再実行で蓄積されます）")

    log.info("")


# =====================================================================
# 5. 買取店間価格差
# =====================================================================

def analyze_shop_gap(df):
    """買取店間の価格差が大きい商品を表示する"""
    log.info("=" * 60)
    log.info("=== 買取店間価格差分析 ===")
    log.info("※ 最高値と2番目の差が大きい = 特定店舗が高く評価している商品")

    if df is None or df.empty:
        log.info("CSVデータがありません")
        return

    items = []
    for _, row in df.iterrows():
        gap = int(row["最高買取価格"]) - int(row.get("2番目価格", 0))
        if gap >= 3000 and int(row["最高買取価格"]) >= 10000:
            items.append({
                "jan": row["JAN"],
                "name": row["商品名"][:35],
                "best": int(row["最高買取価格"]),
                "second": int(row.get("2番目価格", 0)),
                "gap": gap,
                "shop": row["最高値店舗"],
                "shop_count": int(row.get("買取店数", 0)),
            })

    items.sort(key=lambda x: x["gap"], reverse=True)

    log.info("")
    log.info("%-36s %8s %8s %8s %6s %5s", "商品名", "最高値", "2番目", "差額", "店舗", "店数")
    log.info("-" * 76)
    for item in items[:30]:
        log.info("%-36s %7s %7s %+7s %6s %5d",
                 item["name"],
                 f"{item['best']:,}",
                 f"{item['second']:,}",
                 f"{item['gap']:,}",
                 item["shop"],
                 item["shop_count"])

    if items:
        log.info("")
        log.info("合計%d件（差額3,000円以上、買取10,000円以上）", len(items))
    log.info("")


# =====================================================================
# 6. メルカリ相場比較
# =====================================================================

def analyze_mercari(results: list):
    """利益結果の買取価格 vs メルカリ推定相場を比較する

    メルカリの実相場はスクレイピングが必要なため、ここでは
    買取価格の120%を推定メルカリ相場として簡易比較する。
    """
    log.info("=" * 60)
    log.info("=== メルカリ相場比較（推定） ===")
    log.info("※ メルカリ推定相場 = 買取価格 × 120%%（実際の相場は要確認）")

    if not results:
        log.info("利益結果がありません")
        return

    items = []
    for r in results:
        kaitori = r.get("最高買取価格", 0)
        ec_price = r.get("EC最安値", 0)
        if kaitori <= 0 or ec_price <= 0:
            continue

        # 推定メルカリ相場 = 買取価格の120%
        mercari_est = int(kaitori * 1.20)
        mercari = calculate_mercari_profit(ec_price, mercari_est)
        kaitori_profit = r.get("PT込利益", 0)

        items.append({
            "name": r.get("商品名", "")[:30],
            "ec_price": ec_price,
            "kaitori": kaitori,
            "kaitori_profit": kaitori_profit,
            "mercari_est": mercari_est,
            "mercari_profit": mercari["mercari_profit"],
            "mercari_net": mercari["mercari_net"],
            "diff": mercari["mercari_profit"] - kaitori_profit,
        })

    items.sort(key=lambda x: x["diff"], reverse=True)

    log.info("")
    log.info("%-32s %8s %10s %10s %10s", "商品名", "EC価格", "買取PT込", "メルカリ利益", "差額")
    log.info("-" * 72)
    better_mercari = 0
    for item in items[:20]:
        mark = "◎" if item["diff"] > 0 else " "
        if item["diff"] > 0:
            better_mercari += 1
        log.info("%s %-30s %7s %+9s %+9s %+9s",
                 mark, item["name"],
                 f"{item['ec_price']:,}",
                 f"{item['kaitori_profit']:,}円",
                 f"{item['mercari_profit']:,}円",
                 f"{item['diff']:,}円")

    total_better = sum(1 for i in items if i["diff"] > 0)
    log.info("")
    log.info("メルカリ販売がお得な商品: %d/%d件", total_better, len(items))
    log.info("※ 推定相場のため、実際のメルカリ売却済み価格を確認してください")
    log.info("")


# =====================================================================
# メイン
# =====================================================================

def main():
    parser = argparse.ArgumentParser(description="利益分析ツール")
    parser.add_argument("--category", action="store_true", help="カテゴリ別利益率分析")
    parser.add_argument("--reinvest", action="store_true", help="ポイント再投資ROI分析")
    parser.add_argument("--bulk", action="store_true", help="まとめ買いグルーピング")
    parser.add_argument("--trend", action="store_true", help="価格トレンド分析")
    parser.add_argument("--shop-gap", action="store_true", help="買取店間価格差分析")
    parser.add_argument("--mercari", action="store_true", help="メルカリ相場比較（推定）")
    parser.add_argument("--csv", type=str, default="", help="CSVファイルパス（省略時は最新）")
    args = parser.parse_args()

    # 全指定なしなら全分析実行
    run_all = not any([args.category, args.reinvest, args.bulk,
                       args.trend, args.shop_gap, args.mercari])

    # CSV読み込み
    df = None
    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
        csv_path = csv_files[0] if csv_files else None

    if csv_path and csv_path.exists():
        df = load_csv(str(csv_path))
        log.info("CSV: %s (%s件)", csv_path.name, f"{len(df):,}")

    # キャッシュ読み込み
    results = _load_cache()
    ec_cache = _load_ec_cache()
    profitable = [r for r in results if r.get("現金利益", 0) > 0]

    log.info("利益結果: %d件（うち黒字%d件）", len(results), len(profitable))
    log.info("")

    if run_all or args.category:
        analyze_by_category(profitable, df)

    if run_all or args.reinvest:
        analyze_reinvest_roi(profitable)

    if run_all or args.bulk:
        analyze_bulk_buy(profitable)

    if run_all or args.trend:
        analyze_price_trend(ec_cache, profitable, df)

    if run_all or args.shop_gap:
        analyze_shop_gap(df)

    if run_all or args.mercari:
        analyze_mercari(profitable)

    log.info("=== 分析完了 ===")


if __name__ == "__main__":
    main()
