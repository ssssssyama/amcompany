"""価格妥当性フィルタの単一責任モジュール

以前は `ec_search`, `price_server`, `auto_extract.load_cache_clean`,
`price_discrepancy_verifier` の4箇所に同じロジックが分散していた。
閾値調整のたびに同期漏れが発生するため、ここに一元化する。

他のモジュールは本モジュールを import して使うこと:

    from filters import is_suspicious_price_ratio, ratio_threshold

デフォルト値:
- 通常商品: EC/買取 < 0.35 なら除外
- 高額商品（買取10万超）: EC/買取 < 0.50 なら除外（JAN流用誤マッチ対策）

環境変数で調整可:
    KAITORI_RATIO_NORMAL        通常商品の閾値 (default 0.35)
    KAITORI_RATIO_HIGH_VALUE    高額商品の閾値 (default 0.50)
    KAITORI_HIGH_VALUE_KAITORI  高額判定の境界 (default 100_000)
"""

import os

SUSPICIOUS_RATIO_NORMAL = float(os.environ.get("KAITORI_RATIO_NORMAL", "0.35"))
SUSPICIOUS_RATIO_HIGH_VALUE = float(os.environ.get("KAITORI_RATIO_HIGH_VALUE", "0.50"))
HIGH_VALUE_KAITORI_THRESHOLD = int(os.environ.get("KAITORI_HIGH_VALUE_KAITORI", "100000"))


def ratio_threshold(kaitori_price: int) -> float:
    """買取価格から適用される閾値を返す。

    高額商品（10万超）は楽天ショップのJAN流用等でアクセサリ/関連商品の
    格安価格が混入しやすいため、より厳しい50%基準を適用する。
    """
    if kaitori_price >= HIGH_VALUE_KAITORI_THRESHOLD:
        return SUSPICIOUS_RATIO_HIGH_VALUE
    return SUSPICIOUS_RATIO_NORMAL


def is_suspicious_price_ratio(kaitori_price: int, ec_price: int) -> bool:
    """EC価格が買取価格に対して極端に安い場合、誤マッチの疑いあり（除外用）

    具体的な既知パターン:
    - FUJIFILM X100VI(買取293,300) → レンズフィルター(2,790) : ratio 0.01
    - MacBook Pro(買取358,000) → sokutei shop(59,800) : ratio 0.17
    - VIERA TV(買取100,000) → 1V型あたりの価格(3,104) : ratio 0.03

    Args:
        kaitori_price: 買取価格（円）
        ec_price: EC販売価格（円）

    Returns:
        True ならスキップすべき（疑わしい）、False なら採用可能
    """
    if kaitori_price <= 0 or ec_price <= 0:
        return False
    return (ec_price / kaitori_price) < ratio_threshold(kaitori_price)


def check_ratio(kaitori_price: int, ec_price: int) -> dict:
    """詳細判定結果を返すデバッグ/レポート用ヘルパー

    Returns:
        {
            "suspicious": bool,
            "ratio": float,
            "threshold": float,
            "reason": str,
        }
    """
    if kaitori_price <= 0 or ec_price <= 0:
        return {
            "suspicious": False, "ratio": 0.0, "threshold": 0.0,
            "reason": "価格が0以下、判定スキップ",
        }
    ratio = ec_price / kaitori_price
    thr = ratio_threshold(kaitori_price)
    suspicious = ratio < thr
    return {
        "suspicious": suspicious,
        "ratio": round(ratio, 3),
        "threshold": thr,
        "reason": (
            f"EC {ec_price:,}円 / 買取 {kaitori_price:,}円 = {ratio:.3f} "
            f"{'<' if suspicious else '>='} {thr}"
        ),
    }
