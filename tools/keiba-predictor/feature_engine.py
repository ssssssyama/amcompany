"""特徴量エンジニアリング — 各馬の予測用特徴量を計算"""

from data_manager import get_horse_history, get_jockey_history


def _safe_div(a, b, default=0.0):
    return a / b if b > 0 else default


def _classify_running_style(history):
    """過去のコーナー通過順から脚質を分類

    Returns:
        str: "逃げ" / "先行" / "差し" / "追込"
    """
    if not history:
        return "不明"

    early_positions = []
    for r in history[:5]:
        corners = r.get("corner_positions", "")
        if not corners:
            continue
        try:
            first_corner = int(corners.split("-")[0])
            early_positions.append(first_corner)
        except (ValueError, IndexError):
            continue

    if not early_positions:
        return "不明"

    avg = sum(early_positions) / len(early_positions)
    if avg <= 2.0:
        return "逃げ"
    elif avg <= 4.0:
        return "先行"
    elif avg <= 6.0:
        return "差し"
    else:
        return "追込"


def compute_horse_features(races, entry, race_info):
    """1頭分の特徴量を計算

    Args:
        races: 過去レースデータ全体
        entry: 予測対象の1馬エントリ（dict）
        race_info: 予測対象レース情報（dict）

    Returns:
        dict: 特徴量名→値
    """
    horse_id = entry["horse_id"]
    jockey_id = entry["jockey_id"]
    before_date = race_info["race_date"]
    venue = race_info["venue"]
    surface = race_info["surface"]
    distance = race_info["distance"]
    track_condition = race_info["track_condition"]

    horse_hist = get_horse_history(races, horse_id, before_date)
    jockey_hist = get_jockey_history(races, jockey_id, before_date)

    features = {}

    # === 馬の成績（全体）===
    total = len(horse_hist)
    wins = sum(1 for r in horse_hist if r["finish_position"] == 1)
    top3 = sum(1 for r in horse_hist if 1 <= r["finish_position"] <= 3)
    features["horse_win_rate"] = _safe_div(wins, total)
    features["horse_top3_rate"] = _safe_div(top3, total)
    features["horse_total_races"] = total

    # === 馬の成績（直近5走）===
    recent = horse_hist[:5]
    recent_total = len(recent)
    recent_wins = sum(1 for r in recent if r["finish_position"] == 1)
    recent_top3 = sum(1 for r in recent if 1 <= r["finish_position"] <= 3)
    features["horse_win_rate_last5"] = _safe_div(recent_wins, recent_total)
    features["horse_top3_rate_last5"] = _safe_div(recent_top3, recent_total)
    features["horse_avg_position_last5"] = (
        _safe_div(sum(r["finish_position"] for r in recent), recent_total, 10.0)
        if recent else 10.0
    )

    # === 同会場成績 ===
    venue_hist = [r for r in horse_hist if r["venue"] == venue]
    venue_total = len(venue_hist)
    venue_wins = sum(1 for r in venue_hist if r["finish_position"] == 1)
    features["venue_win_rate"] = _safe_div(venue_wins, venue_total)
    features["venue_races"] = venue_total

    # === 同馬場（芝/ダート）成績 ===
    surface_hist = [r for r in horse_hist if r["surface"] == surface]
    surface_total = len(surface_hist)
    surface_wins = sum(1 for r in surface_hist if r["finish_position"] == 1)
    features["surface_win_rate"] = _safe_div(surface_wins, surface_total)

    # === 同距離帯成績（±200m）===
    dist_hist = [r for r in horse_hist if abs(r["distance"] - distance) <= 200]
    dist_total = len(dist_hist)
    dist_wins = sum(1 for r in dist_hist if r["finish_position"] == 1)
    features["distance_win_rate"] = _safe_div(dist_wins, dist_total)

    # === 同馬場状態成績 ===
    cond_hist = [r for r in horse_hist if r["track_condition"] == track_condition]
    cond_total = len(cond_hist)
    cond_top3 = sum(1 for r in cond_hist if 1 <= r["finish_position"] <= 3)
    features["condition_top3_rate"] = _safe_div(cond_top3, cond_total)

    # === 上がり3F平均（直近5走）===
    last3f_values = [r["last_3f"] for r in recent if r["last_3f"] > 0]
    features["avg_last_3f"] = (
        sum(last3f_values) / len(last3f_values) if last3f_values else 36.0
    )

    # === 脚質 ===
    running_style = _classify_running_style(horse_hist)
    features["running_style"] = running_style
    # 脚質スコア（会場・距離による有利不利の簡易推定）
    style_bonus = {"逃げ": 0.0, "先行": 0.05, "差し": 0.03, "追込": -0.02, "不明": 0.0}
    if distance >= 2000:
        style_bonus = {"逃げ": -0.03, "先行": 0.03, "差し": 0.05, "追込": 0.02, "不明": 0.0}
    features["running_style_score"] = style_bonus.get(running_style, 0.0)

    # === 騎手成績 ===
    j_total = len(jockey_hist)
    j_wins = sum(1 for r in jockey_hist if r["finish_position"] == 1)
    j_top3 = sum(1 for r in jockey_hist if 1 <= r["finish_position"] <= 3)
    features["jockey_win_rate"] = _safe_div(j_wins, j_total)
    features["jockey_top3_rate"] = _safe_div(j_top3, j_total)

    # === 騎手の同会場成績 ===
    j_venue = [r for r in jockey_hist if r["venue"] == venue]
    j_venue_total = len(j_venue)
    j_venue_wins = sum(1 for r in j_venue if r["finish_position"] == 1)
    features["jockey_venue_win_rate"] = _safe_div(j_venue_wins, j_venue_total)

    # === 枠順バイアス ===
    gate = entry["gate_number"]
    # 簡易モデル: 小回りコースは内枠有利、直線長いコースはフラット
    if venue in ("中山", "小倉", "福島"):
        gate_score = max(0.0, 0.1 - (gate - 1) * 0.02)
    else:
        gate_score = 0.0
    features["gate_bias_score"] = gate_score

    # === 斤量 ===
    base_weight = 57.0 if "牡" in entry.get("sex_age", "") else 55.0
    features["weight_diff"] = entry["weight"] - base_weight

    # === 馬体重変動 ===
    features["horse_weight_change"] = entry.get("horse_weight_diff", 0)

    # === 休養日数 ===
    if horse_hist:
        try:
            from datetime import datetime
            last_date = datetime.strptime(horse_hist[0]["race_date"], "%Y-%m-%d")
            target_date = datetime.strptime(before_date, "%Y-%m-%d")
            rest_days = (target_date - last_date).days
        except (ValueError, KeyError):
            rest_days = 30
    else:
        rest_days = 365
    # 適度な休養（14〜60日）が好ましい
    if 14 <= rest_days <= 60:
        features["rest_score"] = 0.05
    elif rest_days < 14:
        features["rest_score"] = -0.03
    elif rest_days <= 120:
        features["rest_score"] = 0.0
    else:
        features["rest_score"] = -0.05
    features["rest_days"] = rest_days

    return features


def compute_all_features(races, upcoming_entries, race_info):
    """全出走馬の特徴量を計算

    Returns:
        list[dict]: 各馬の特徴量辞書のリスト（horse_name, horse_number含む）
    """
    results = []
    for entry in upcoming_entries:
        features = compute_horse_features(races, entry, race_info)
        features["horse_name"] = entry["horse_name"]
        features["horse_number"] = entry["horse_number"]
        features["horse_id"] = entry["horse_id"]
        features["jockey_name"] = entry["jockey_name"]
        results.append(features)
    return results
