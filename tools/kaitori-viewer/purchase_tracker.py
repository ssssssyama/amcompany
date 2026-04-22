"""実購入・実売却履歴の追跡モジュール

利益候補（cache_results）はあくまで「予想」値。
実際に購入できたか・いくらで売却できたかを記録し、
戦略の精度を継続的に改善するためのデータ基盤。

使い方:
    from purchase_tracker import log_purchase, log_sale, get_actual_stats

    # 購入を記録
    log_purchase(jan="4549292167382", actual_price=95980, shop="楽天",
                 shipping=1000, source_strategy="kaitori-up")

    # 売却を記録（買取店 or メルカリ）
    log_sale(jan="4549292167382", actual_price=110000, channel="buyback",
             shop="ルデヤ", fee=0)

    # 統計
    stats = get_actual_stats()
    # {"total_purchases": 5, "total_sales": 3, "net_profit": 42000,
    #  "avg_profit_per_trade": 14000, ...}

CLI:
    python purchase_tracker.py --log-purchase 4549292167382 95980 楽天
    python purchase_tracker.py --stats
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_TRADES_FILE = Path.home() / ".kaitori-viewer" / "actual_trades.json"


def _load_trades() -> dict:
    if not _TRADES_FILE.exists():
        return {"purchases": [], "sales": []}
    try:
        data = json.loads(_TRADES_FILE.read_text(encoding="utf-8"))
        data.setdefault("purchases", [])
        data.setdefault("sales", [])
        return data
    except (json.JSONDecodeError, OSError):
        return {"purchases": [], "sales": []}


def _save_trades(data: dict) -> None:
    _TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TRADES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def log_purchase(
    jan: str,
    actual_price: int,
    shop: str = "",
    shipping: int = 0,
    points_earned: int = 0,
    card_rebate: int = 0,
    source_strategy: str = "",
    note: str = "",
) -> None:
    """商品購入を記録する。

    Args:
        jan: JANコード
        actual_price: 実購入価格（ポイント・クーポン適用後）
        shop: 購入ショップ
        shipping: 送料
        points_earned: 獲得ポイント
        card_rebate: カード還元額
        source_strategy: どの戦略で発見した候補か（E/P/I等）
        note: 任意メモ
    """
    data = _load_trades()
    data["purchases"].append({
        "jan": jan,
        "price": int(actual_price),
        "shop": shop,
        "shipping": int(shipping),
        "points_earned": int(points_earned),
        "card_rebate": int(card_rebate),
        "source_strategy": source_strategy,
        "note": note,
        "date": datetime.now().isoformat(timespec="seconds"),
    })
    _save_trades(data)
    logger.info("[購入記録] %s %s円 @ %s", jan, f"{actual_price:,}", shop)


def log_sale(
    jan: str,
    actual_price: int,
    channel: str = "buyback",
    shop: str = "",
    fee: int = 0,
    shipping: int = 0,
    note: str = "",
) -> None:
    """商品売却を記録する。

    Args:
        jan: JANコード
        actual_price: 実売却価格（手数料・送料引き前の提示価格）
        channel: "buyback"（買取店）or "mercari"（メルカリ）or "yauc"（ヤフオク）等
        shop: 売却先ショップ/プラットフォーム
        fee: 販売手数料（メルカリ10%等）
        shipping: 発送料
        note: 任意メモ
    """
    data = _load_trades()
    data["sales"].append({
        "jan": jan,
        "price": int(actual_price),
        "channel": channel,
        "shop": shop,
        "fee": int(fee),
        "shipping": int(shipping),
        "note": note,
        "date": datetime.now().isoformat(timespec="seconds"),
    })
    _save_trades(data)
    logger.info("[売却記録] %s %s円 @ %s (%s)", jan, f"{actual_price:,}", shop, channel)


def get_trade_pairs() -> list[dict]:
    """購入と売却のペアを作って、実利益を計算する。

    同一JANの最初の購入と最初の売却をペアにする（FIFO）。
    複数回購入・売却がある場合は最新まで対応。

    Returns:
        [{jan, purchase_price, sale_price, actual_profit, purchase_strategy, ...}]
    """
    data = _load_trades()
    purchases = sorted(data["purchases"], key=lambda x: x.get("date", ""))
    sales = sorted(data["sales"], key=lambda x: x.get("date", ""))

    # JANごとにFIFOでマッチ
    by_jan: dict[str, dict] = {"purchases": {}, "sales": {}}
    for p in purchases:
        by_jan["purchases"].setdefault(p["jan"], []).append(p)
    for s in sales:
        by_jan["sales"].setdefault(s["jan"], []).append(s)

    pairs = []
    for jan, plist in by_jan["purchases"].items():
        slist = by_jan["sales"].get(jan, [])
        for i, p in enumerate(plist):
            s = slist[i] if i < len(slist) else None
            if not s:
                # 売却未完了
                continue
            actual_profit = (
                s["price"]
                - s.get("fee", 0)
                - s.get("shipping", 0)
                - p["price"]
                - p.get("shipping", 0)
                + p.get("points_earned", 0)
                + p.get("card_rebate", 0)
            )
            pairs.append({
                "jan": jan,
                "purchase_price": p["price"],
                "purchase_shop": p.get("shop", ""),
                "purchase_strategy": p.get("source_strategy", ""),
                "sale_price": s["price"],
                "sale_channel": s.get("channel", ""),
                "sale_shop": s.get("shop", ""),
                "actual_profit": actual_profit,
                "purchase_date": p.get("date", ""),
                "sale_date": s.get("date", ""),
            })
    return pairs


def get_actual_stats() -> dict:
    """全体統計を返す"""
    data = _load_trades()
    pairs = get_trade_pairs()
    completed = [p for p in pairs if p.get("actual_profit") is not None]
    total_profit = sum(p["actual_profit"] for p in completed)
    # 戦略別集計
    by_strategy: dict[str, dict] = {}
    for p in completed:
        s = p.get("purchase_strategy", "unknown")
        b = by_strategy.setdefault(s, {"count": 0, "profit": 0})
        b["count"] += 1
        b["profit"] += p["actual_profit"]
    # チャネル別集計
    by_channel: dict[str, dict] = {}
    for p in completed:
        c = p.get("sale_channel", "unknown")
        b = by_channel.setdefault(c, {"count": 0, "profit": 0})
        b["count"] += 1
        b["profit"] += p["actual_profit"]

    return {
        "total_purchases": len(data["purchases"]),
        "total_sales": len(data["sales"]),
        "completed_trades": len(completed),
        "total_profit": total_profit,
        "avg_profit_per_trade": total_profit // len(completed) if completed else 0,
        "best_trade": max(completed, key=lambda x: x["actual_profit"]) if completed else None,
        "by_strategy": by_strategy,
        "by_channel": by_channel,
    }


def get_profitable_jans() -> set[str]:
    """実際に利益が出たJANの集合（戦略Aの精度向上用）"""
    pairs = get_trade_pairs()
    return {p["jan"] for p in pairs if p.get("actual_profit", 0) > 0}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="実購入・売却履歴トラッカー")
    sub = parser.add_subparsers(dest="cmd")

    p_buy = sub.add_parser("buy", help="購入記録")
    p_buy.add_argument("jan")
    p_buy.add_argument("price", type=int)
    p_buy.add_argument("shop")
    p_buy.add_argument("--strategy", default="")
    p_buy.add_argument("--shipping", type=int, default=0)
    p_buy.add_argument("--points", type=int, default=0)
    p_buy.add_argument("--rebate", type=int, default=0)

    p_sell = sub.add_parser("sell", help="売却記録")
    p_sell.add_argument("jan")
    p_sell.add_argument("price", type=int)
    p_sell.add_argument("channel", choices=["buyback", "mercari", "yauc", "other"])
    p_sell.add_argument("shop")
    p_sell.add_argument("--fee", type=int, default=0)
    p_sell.add_argument("--shipping", type=int, default=0)

    sub.add_parser("stats", help="統計表示")
    sub.add_parser("pairs", help="購入-売却ペア一覧")

    args = parser.parse_args()

    if args.cmd == "buy":
        log_purchase(args.jan, args.price, args.shop,
                     shipping=args.shipping, points_earned=args.points,
                     card_rebate=args.rebate, source_strategy=args.strategy)
    elif args.cmd == "sell":
        log_sale(args.jan, args.price, args.channel, args.shop,
                 fee=args.fee, shipping=args.shipping)
    elif args.cmd == "pairs":
        for p in get_trade_pairs():
            print(f"  {p['jan']}: 購入{p['purchase_price']:,}円 → "
                  f"売却{p['sale_price']:,}円 = 利益{p['actual_profit']:+,}円 "
                  f"[{p.get('purchase_strategy', '?')}/{p.get('sale_channel', '?')}]")
    elif args.cmd == "stats":
        s = get_actual_stats()
        print(f"=== 実績統計 ===")
        print(f"  購入数: {s['total_purchases']}件")
        print(f"  売却数: {s['total_sales']}件")
        print(f"  完了取引: {s['completed_trades']}件")
        print(f"  総利益: {s['total_profit']:+,}円")
        if s['completed_trades']:
            print(f"  平均利益: {s['avg_profit_per_trade']:+,}円/件")
            if s['best_trade']:
                bt = s['best_trade']
                print(f"  ベスト: {bt['jan']} {bt['actual_profit']:+,}円 "
                      f"({bt.get('purchase_strategy', '?')}/{bt.get('sale_channel', '?')})")
        print(f"\n=== 戦略別 ===")
        for st, d in sorted(s['by_strategy'].items(), key=lambda x: -x[1]['profit']):
            print(f"  {st}: {d['count']}件 → {d['profit']:+,}円")
        print(f"\n=== 売却チャネル別 ===")
        for ch, d in sorted(s['by_channel'].items(), key=lambda x: -x[1]['profit']):
            print(f"  {ch}: {d['count']}件 → {d['profit']:+,}円")
    else:
        parser.print_help()
