"""現金利益の計算"""


def calculate_cash_profit(
    kaitori_price: int,
    ec_price: int,
    shipping_cost: int = 0,
    points: int = 0,
    coupon: int = 0,
) -> dict:
    """現金利益を計算する

    Args:
        kaitori_price: 買取価格（最高値）
        ec_price: EC最安値（購入価格）
        shipping_cost: 送料+手数料の合計（EC送料 + 買取発送料）
        points: 獲得ポイント
        coupon: クーポン割引額（EC価格から差し引かれる）

    Returns:
        cash_profit: 現金利益 = 買取価格 - (EC価格 - クーポン) - 送料
        profit_with_points: ポイント込み利益
        roi: 投資利益率(%)
        is_profitable: 現金利益が出るか
        effective_price: 実質購入価格 = EC価格 - クーポン
    """
    effective_price = ec_price - coupon
    cash_profit = kaitori_price - effective_price - shipping_cost
    profit_with_points = cash_profit + points
    total_cost = effective_price + shipping_cost
    roi = (cash_profit / total_cost * 100) if total_cost > 0 else 0.0

    return {
        "cash_profit": cash_profit,
        "profit_with_points": profit_with_points,
        "roi": round(roi, 1),
        "is_profitable": cash_profit > 0,
        "effective_price": effective_price,
    }


def is_above_threshold(
    kaitori_price: int,
    ec_price: int,
    threshold: int,
    shipping_cost: int = 0,
    coupon: int = 0,
) -> bool:
    """現金利益が閾値以上かどうかを判定する"""
    effective_price = ec_price - coupon
    return (kaitori_price - effective_price - shipping_cost) >= threshold


def calculate_reinvest_roi(
    kaitori_price: int,
    ec_price: int,
    shipping_cost: int = 0,
    points: int = 0,
    coupon: int = 0,
) -> dict:
    """ポイント再投資を前提としたROIを計算する

    獲得ポイントを次回仕入れに充当する前提で、
    実質的な仕入れコストを下げた場合のROIを算出。

    Returns:
        reinvest_roi: ポイント再投資込みROI(%)
        reinvest_cost: ポイント充当後の実質仕入れ原価
    """
    effective_price = ec_price - coupon
    total_cost = effective_price + shipping_cost
    reinvest_cost = total_cost - points  # ポイントを次回原価から差し引く
    cash_profit = kaitori_price - effective_price - shipping_cost
    reinvest_roi = (cash_profit / reinvest_cost * 100) if reinvest_cost > 0 else 0.0

    return {
        "reinvest_roi": round(reinvest_roi, 1),
        "reinvest_cost": reinvest_cost,
    }


def calculate_mercari_profit(
    ec_price: int,
    mercari_price: int,
    shipping_cost: int = 800,
    mercari_fee_rate: float = 0.10,
) -> dict:
    """メルカリ販売時の利益を計算する

    Args:
        ec_price: EC仕入れ価格
        mercari_price: メルカリ販売価格（売却済み相場）
        shipping_cost: メルカリ配送料（デフォルト800円、らくらくメルカリ便）
        mercari_fee_rate: メルカリ手数料率（10%）

    Returns:
        mercari_profit: メルカリ販売利益
        mercari_net: メルカリ手取り額（手数料・送料差し引き後）
    """
    fee = int(mercari_price * mercari_fee_rate)
    net = mercari_price - fee - shipping_cost
    profit = net - ec_price

    return {
        "mercari_profit": profit,
        "mercari_net": net,
        "mercari_fee": fee,
    }
