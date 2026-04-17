"""楽天・Yahoo!ショッピングのキャンペーンカレンダー

当日のキャンペーン状況からボーナスポイント率を自動算出する。
手動で --rakuten-bonus / --yahoo-bonus を指定する代わりに使用。
"""

from datetime import date, datetime


def _is_rakuten_marathon(today: date) -> bool:
    """楽天お買い物マラソン判定（毎月前半 4-11日頃が多い）

    正確な日程はAPIで取得できないため、典型的な開催パターンで近似。
    楽天は月1回、前半に4-11日間開催する傾向。
    """
    return 4 <= today.day <= 11


def _is_rakuten_super_sale(today: date) -> bool:
    """楽天スーパーSALE判定（3月・6月・9月・12月の前半）"""
    return today.month in (3, 6, 9, 12) and 4 <= today.day <= 11


def _is_5_or_0_day(today: date) -> bool:
    """5と0のつく日（楽天・Yahoo共通でポイントアップ）"""
    return today.day % 5 == 0


def _is_sunday(today: date) -> bool:
    """日曜日（Yahoo!ショッピングでポイントアップ）"""
    return today.weekday() == 6


def get_rakuten_bonus(today: date | None = None, spu_rate: float = 3.0) -> float:
    """楽天の当日ボーナスポイント率（%）を算出する

    Args:
        today: 判定日（Noneなら当日）
        spu_rate: ユーザーのSPU倍率（デフォルト3.0%）

    Returns:
        ボーナスポイント率（%）。基本1%は含まない。
    """
    if today is None:
        today = date.today()

    bonus = spu_rate  # SPU基本

    if _is_5_or_0_day(today):
        bonus += 2.0  # 5と0のつく日

    if _is_rakuten_super_sale(today):
        bonus += 5.0  # スーパーSALE（買い回り平均を想定）
    elif _is_rakuten_marathon(today):
        bonus += 4.0  # マラソン（買い回り平均を想定）

    return bonus


def get_yahoo_bonus(today: date | None = None, softbank_user: bool = False) -> float:
    """Yahoo!ショッピングの当日ボーナスポイント率（%）を算出する

    Args:
        today: 判定日（Noneなら当日）
        softbank_user: ソフトバンク/ワイモバイルユーザーか

    Returns:
        ボーナスポイント率（%）。基本1%は含まない。
    """
    if today is None:
        today = date.today()

    bonus = 0.0

    if _is_sunday(today):
        bonus += 10.0 if softbank_user else 5.0

    if _is_5_or_0_day(today):
        bonus += 4.0  # 5のつく日キャンペーン

    return bonus


def get_bonus_rates(today: date | None = None, spu_rate: float = 3.0,
                    softbank_user: bool = False) -> dict:
    """楽天・Yahooの当日ボーナス率をまとめて返す"""
    if today is None:
        today = date.today()

    return {
        "rakuten": get_rakuten_bonus(today, spu_rate),
        "yahoo": get_yahoo_bonus(today, softbank_user),
        "date": today.isoformat(),
        "campaigns": get_active_campaigns(today),
    }


def get_active_campaigns(today: date | None = None) -> list[str]:
    """当日のアクティブなキャンペーン名を返す"""
    if today is None:
        today = date.today()

    campaigns = []
    if _is_rakuten_super_sale(today):
        campaigns.append("楽天スーパーSALE")
    elif _is_rakuten_marathon(today):
        campaigns.append("楽天お買い物マラソン")
    if _is_5_or_0_day(today):
        campaigns.append("5と0のつく日")
    if _is_sunday(today):
        campaigns.append("Yahoo!日曜日")

    return campaigns


if __name__ == "__main__":
    rates = get_bonus_rates()
    print(f"日付: {rates['date']}")
    print(f"楽天ボーナス: {rates['rakuten']:.1f}%")
    print(f"Yahooボーナス: {rates['yahoo']:.1f}%")
    if rates["campaigns"]:
        print(f"キャンペーン: {', '.join(rates['campaigns'])}")
    else:
        print("キャンペーン: なし")
