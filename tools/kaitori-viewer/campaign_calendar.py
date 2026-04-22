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


# --- 戦略L: 季節・イベント商戦自動検知 ---

# (月, キーワード) → ブースト倍率
# キーワードはカテゴリ名 or 商品名のいずれかにマッチすれば適用
_SEASONAL_BOOST_MAP: dict[tuple[int, str], float] = {
    # 1月: 福袋・新生活準備
    (1, "福袋"): 1.4, (1, "おせち"): 1.3,
    # 2月: バレンタイン・春準備
    (2, "チョコ"): 1.2, (2, "新生活"): 1.2,
    # 3月: 新生活ピーク
    (3, "新生活"): 1.5, (3, "炊飯器"): 1.4, (3, "冷蔵庫"): 1.4,
    (3, "洗濯機"): 1.4, (3, "電子レンジ"): 1.3, (3, "掃除機"): 1.3,
    # 4月: 新生活継続
    (4, "新生活"): 1.4, (4, "GW"): 1.3, (4, "アウトドア"): 1.2,
    # 5月: GW・夏準備
    (5, "GW"): 1.4, (5, "アウトドア"): 1.4, (5, "扇風機"): 1.3,
    (5, "エアコン"): 1.3, (5, "キャンプ"): 1.3,
    # 6月: 梅雨・本格的な夏家電需要
    (6, "扇風機"): 1.5, (6, "エアコン"): 1.5, (6, "除湿"): 1.4,
    (6, "梅雨"): 1.3,
    # 7月: 真夏ピーク
    (7, "夏"): 1.5, (7, "扇風機"): 1.4, (7, "エアコン"): 1.4,
    (7, "アウトドア"): 1.3, (7, "ビアサーバー"): 1.3,
    # 8月: お盆・帰省・夏休み
    (8, "夏"): 1.4, (8, "アウトドア"): 1.3, (8, "カメラ"): 1.2,
    # 9月: 新学期・iPhone新型
    (9, "新学期"): 1.3, (9, "iPhone"): 1.4, (9, "Apple"): 1.3,
    # 10月: 暖房準備
    (10, "ストーブ"): 1.5, (10, "ヒーター"): 1.5, (10, "暖房"): 1.4,
    (10, "こたつ"): 1.3, (10, "電気毛布"): 1.3,
    # 11月: クリスマス商戦・ボーナス前
    (11, "クリスマス"): 1.4, (11, "ゲーム"): 1.3, (11, "Switch"): 1.3,
    (11, "暖房"): 1.4, (11, "おもちゃ"): 1.3,
    # 12月: ボーナス・年末ギフト・福袋準備
    (12, "ゲーム"): 1.5, (12, "Switch"): 1.5, (12, "PS5"): 1.5,
    (12, "イヤホン"): 1.3, (12, "ヘッドホン"): 1.3, (12, "カメラ"): 1.4,
    (12, "クリスマス"): 1.5, (12, "おせち"): 1.3,
}


def get_seasonal_boost(category: str = "", name: str = "", today: date | None = None) -> float:
    """戦略L: 現在月とカテゴリ/商品名に応じた季節ブースト係数（1.0〜1.5）

    Args:
        category: カテゴリ名（CSV の「カテゴリ」列）
        name: 商品名（任意、カテゴリと併せて判定）
        today: 判定日（Noneなら当日）

    Returns:
        最大ブースト倍率。マッチなしは 1.0
    """
    if today is None:
        today = date.today()
    haystack = f"{category} {name}".lower()
    if not haystack.strip():
        return 1.0

    # 当月 + 翌月の両方を見て先取り需要も拾う
    boost = 1.0
    for month_offset in (0, 1):
        target_month = ((today.month - 1 + month_offset) % 12) + 1
        for (month, keyword), rate in _SEASONAL_BOOST_MAP.items():
            if month != target_month:
                continue
            if keyword.lower() in haystack:
                # 翌月マッチは効果半減（先取り）
                effective = rate if month_offset == 0 else 1.0 + (rate - 1.0) * 0.5
                boost = max(boost, effective)
    return boost


if __name__ == "__main__":
    rates = get_bonus_rates()
    print(f"日付: {rates['date']}")
    print(f"楽天ボーナス: {rates['rakuten']:.1f}%")
    print(f"Yahooボーナス: {rates['yahoo']:.1f}%")
    if rates["campaigns"]:
        print(f"キャンペーン: {', '.join(rates['campaigns'])}")
    else:
        print("キャンペーン: なし")

    print(f"\n=== 戦略L: 季節ブースト ===")
    samples = [
        ("ゲーム", "Nintendo Switch"),
        ("カメラ", "Sony α7"),
        ("家電", "扇風機"),
        ("家電", "ストーブ"),
        ("その他", "RTX5090"),
    ]
    for cat, name in samples:
        b = get_seasonal_boost(cat, name)
        print(f"  {cat}/{name}: x{b:.2f}")
