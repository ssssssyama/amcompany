"""現金利益の計算"""

# 決済手段・カード別の還元率（EC最安値ソースごと）
# 「このソースで買うときにこのカード/決済を使うと何%還元か」
_PAYMENT_REBATE_BY_SOURCE = {
    # 楽天市場: 楽天カード 1% + SPU変動（運用では楽天ボーナスPT と合算するのでここでは基本分のみ）
    "楽天": 0.01,
    # Yahoo!ショッピング: PayPayカード 3% or PayPay残高
    "Yahoo": 0.03,
    # Amazon: Amazon Mastercard ゴールド 2%
    "Amazon": 0.02,
    # ヨドバシ: ゴールドポイントカード 10%（実質）
    "ヨドバシ": 0.10,
    # 価格.com経由: 購入サイトによる、汎用1%
    "価格.com": 0.01,
    # Qoo10: Qoo10ポイント
    "Qoo10": 0.02,
    # 量販店Chrome拡張系
    "ビックカメラ": 0.10,     # ビックカメラSuicaカード 10%
    "ジョーシン": 0.02,       # JoshinPointカード 2%
    "ノジマ": 0.03,           # ノジマスーパーポイント
    "ケーズデンキ": 0.01,     # 「あんしんパスポート」分
    "エディオン": 0.01,
    "コジマ": 0.05,           # コジマ・ビックポイント
    "ソフマップ": 0.05,
    "auPAYマーケット": 0.03,  # au PAYカード
    "ツクモ": 0.01,           # ツクモポイント
    "ドスパラ": 0.01,         # ドスパラポイント
    "セブンネット": 0.01,     # nanaco
    "フジヤカメラ": 0.005,    # 現金値引き中心
    "楽天ブックス": 0.01,     # 楽天カード（別途SPUあり）
}
# ベースカード還元（どのサイトでも効く汎用カード、1%還元）
_BASE_CARD_REBATE = 0.01


def calculate_card_rebate(ec_price: int, source: str) -> int:
    """EC購入時のカード・ポイント還元額（円）を計算。

    Args:
        ec_price: EC購入価格
        source: EC サイト名（"楽天", "Yahoo", "Amazon" 等）

    Returns:
        還元額（円、整数切り捨て）
    """
    if ec_price <= 0:
        return 0
    rate = _PAYMENT_REBATE_BY_SOURCE.get(source, _BASE_CARD_REBATE)
    return int(ec_price * rate)


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


def calculate_total_profit(
    kaitori_price: int,
    ec_price: int,
    source: str,
    shipping_cost: int = 0,
    points: int = 0,
    coupon: int = 0,
) -> dict:
    """ポイント + カード還元を含めた実質利益を計算する。

    Args:
        kaitori_price: 買取価格
        ec_price: EC最安値
        source: EC ソース名（カード還元率のルックアップ用）
        shipping_cost: 送料合計
        points: EC側ポイント獲得額
        coupon: クーポン割引額

    Returns:
        既存の calculate_cash_profit 結果 + card_rebate / profit_with_card_rebate / total_profit
    """
    base = calculate_cash_profit(kaitori_price, ec_price, shipping_cost, points, coupon)
    card_rebate = calculate_card_rebate(ec_price - coupon, source)
    base["card_rebate"] = card_rebate
    base["profit_with_card_rebate"] = base["cash_profit"] + card_rebate
    # 総合: 現金利益 + ポイント + カード還元（ただしポイントと還元が重複する場合は少し過大評価になる）
    base["total_profit"] = base["cash_profit"] + points + card_rebate
    # 総合ROI
    total_cost = (ec_price - coupon) + shipping_cost
    if total_cost > 0:
        base["total_roi"] = round(base["total_profit"] / total_cost * 100, 1)
    else:
        base["total_roi"] = 0.0
    return base


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


# カテゴリごとのメルカリ相場係数（買取価格を基準に係数を掛けた値を想定メルカリ価格とする）
# 個人売買（メルカリ）は買取店より高値になる傾向あり、カテゴリ別に経験則で設定
_MERCARI_CATEGORY_RATIO = {
    "カメラ": 1.35,        # カメラ本体・レンズは人気で+35%程度
    "レンズ": 1.40,
    "デジタル一眼": 1.35,
    "ミラーレス": 1.35,
    "ゲーム": 1.25,        # 新作ゲームは+25%
    "Nintendo Switch": 1.30,
    "プレイステーション": 1.30,
    "グラフィックボード": 1.15,  # 供給多めで小さめの差
    "時計": 1.50,          # 高級時計は個人売買でプレミア大
    "ブランド": 1.45,       # ブランド物
    "フィギュア": 1.60,     # コレクターズアイテム
    "トレーディングカード": 1.80,  # トレカは個人売買で爆発的に上がる
    "楽器": 1.30,
    "オーディオ": 1.35,
    "PC": 1.25,
    "パソコン": 1.25,
}
_MERCARI_DEFAULT_RATIO = 1.20  # カテゴリ未定義時のデフォルト


def _estimate_mercari_price(kaitori_price: int, category: str = "") -> int:
    """買取価格から想定メルカリ販売価格を推定"""
    if kaitori_price <= 0:
        return 0
    ratio = _MERCARI_DEFAULT_RATIO
    for kw, r in _MERCARI_CATEGORY_RATIO.items():
        if kw in (category or ""):
            ratio = max(ratio, r)  # より高い係数を採用
    return int(kaitori_price * ratio)


def decide_sell_channel(
    kaitori_price: int,
    ec_price: int,
    category: str = "",
    shipping_cost: int = 1000,
    points: int = 0,
    coupon: int = 0,
    mercari_shipping: int = 800,
    mercari_fee_rate: float = 0.10,
) -> dict:
    """買取店売却 vs メルカリ転売 の利益を比較し、最適な売却チャネルを返す。

    Returns:
        {
            "recommended": "buyback" | "mercari",
            "buyback_profit": int,     # 買取店売却時の現金利益
            "mercari_profit": int,     # メルカリ転売時の利益
            "mercari_estimate": int,   # 想定メルカリ販売価格
            "advantage": int,          # 推奨チャネルの利益差（円）
            "category_ratio": float,   # 適用されたメルカリ係数
        }
    """
    # 買取店ルート
    buyback = calculate_cash_profit(kaitori_price, ec_price, shipping_cost, points, coupon)
    # メルカリルート（カテゴリ別係数で想定価格を算出）
    mercari_estimate = _estimate_mercari_price(kaitori_price, category)
    mercari = calculate_mercari_profit(
        ec_price=ec_price - coupon,  # クーポン適用後価格が仕入原価
        mercari_price=mercari_estimate,
        shipping_cost=mercari_shipping,
        mercari_fee_rate=mercari_fee_rate,
    )

    buyback_profit = buyback["cash_profit"]
    mercari_profit = mercari["mercari_profit"]

    if mercari_profit > buyback_profit:
        recommended = "mercari"
        advantage = mercari_profit - buyback_profit
    else:
        recommended = "buyback"
        advantage = buyback_profit - mercari_profit

    # 適用された係数を算出
    ratio = _MERCARI_DEFAULT_RATIO
    for kw, r in _MERCARI_CATEGORY_RATIO.items():
        if kw in (category or ""):
            ratio = max(ratio, r)

    return {
        "recommended": recommended,
        "buyback_profit": buyback_profit,
        "mercari_profit": mercari_profit,
        "mercari_estimate": mercari_estimate,
        "advantage": advantage,
        "category_ratio": ratio,
    }
