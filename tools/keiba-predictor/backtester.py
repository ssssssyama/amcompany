"""バックテストエンジン — 過去データで予測精度を検証"""

from collections import defaultdict
from feature_engine import compute_all_features
from predictor import StatisticalPredictor, MLPredictor
from data_manager import get_race_info


def run_backtest(races, method="stat", model_path=None, min_history_races=3):
    """全レースに対してバックテストを実行

    各レースについて、それ以前のデータのみで特徴量を計算→予測→実績比較する。
    compute_all_features() が内部で before_date フィルタを使うため
    データリーケージは発生しない。

    Args:
        races: 全過去レースデータ（list[dict]）
        method: "stat" or "ml"
        model_path: MLモデルのパス（method="ml"時）
        min_history_races: スキップ閾値（履歴レース数がこれ未満ならスキップ）

    Returns:
        dict: {total_races, skipped_races, results, summary, method}
    """
    # レースIDでグループ化
    race_groups = {}
    for r in races:
        rid = r["race_id"]
        if rid not in race_groups:
            race_groups[rid] = []
        race_groups[rid].append(r)

    # race_date昇順にソート
    sorted_race_ids = sorted(race_groups.keys(), key=lambda rid: race_groups[rid][0]["race_date"])

    # 予測器の準備
    if method == "ml":
        predictor = MLPredictor()
        predictor.load(model_path)
    else:
        predictor = StatisticalPredictor()

    results = []
    skipped = 0

    for i, rid in enumerate(sorted_race_ids):
        entries = race_groups[rid]
        race_date = entries[0]["race_date"]

        # このレースより前のデータだけを履歴とする
        history = [r for r in races if r["race_date"] < race_date and r["finish_position"] > 0]

        # 履歴が十分か確認
        history_race_ids = set(r["race_id"] for r in history)
        if len(history_race_ids) < min_history_races:
            skipped += 1
            continue

        # レース情報
        race_info = {
            "race_id": entries[0]["race_id"],
            "race_date": entries[0]["race_date"],
            "venue": entries[0]["venue"],
            "race_number": entries[0]["race_number"],
            "race_name": entries[0]["race_name"],
            "grade": entries[0]["grade"],
            "distance": entries[0]["distance"],
            "surface": entries[0]["surface"],
            "track_condition": entries[0]["track_condition"],
            "weather": entries[0]["weather"],
        }

        # 特徴量計算 → 予測
        try:
            features = compute_all_features(history, entries, race_info)
            ranked = predictor.predict(features)
        except Exception as e:
            print(f"  警告: {rid} の予測に失敗（スキップ）: {e}")
            skipped += 1
            continue

        # 評価
        result = evaluate_race(ranked, entries, race_info)
        results.append(result)

        # 進捗表示
        evaluated = len(results)
        total = len(sorted_race_ids) - skipped
        if evaluated % 5 == 0 or evaluated == 1:
            print(f"  {evaluated}レース評価済み...")

    summary = compute_summary(results)
    return {
        "total_races": len(results),
        "skipped_races": skipped,
        "results": results,
        "summary": summary,
        "method": method,
    }


def evaluate_race(ranked, actual_entries, race_info):
    """1レースの予測精度を評価"""
    # 実際の着順マップ: horse_number → finish_position
    actual_map = {}
    odds_map = {}
    for e in actual_entries:
        if e["finish_position"] > 0:
            actual_map[e["horse_number"]] = e["finish_position"]
            odds_map[e["horse_number"]] = e.get("odds", 0.0)

    # 実際の上位3頭
    actual_top3 = set()
    actual_winner = None
    actual_1st_2nd = []
    for num, pos in sorted(actual_map.items(), key=lambda x: x[1]):
        if pos == 1:
            actual_winner = num
        if pos <= 3:
            actual_top3.add(num)
        if pos <= 2:
            actual_1st_2nd.append(num)

    # 予測上位
    pred_nums = [h["horse_number"] for h in ranked]
    pred_top1 = pred_nums[0] if pred_nums else None
    pred_top2 = pred_nums[:2]
    pred_top3 = set(pred_nums[:3])

    # 本命の実際着順
    honmei_actual_pos = actual_map.get(pred_top1, 99)

    # 的中判定
    win_hit = pred_top1 == actual_winner
    place_hit = pred_top1 in actual_top3
    top3_hit = len(pred_top3 & actual_top3)
    trifecta_hit = pred_top3 == actual_top3
    exacta_hit = (
        len(pred_top2) >= 2 and len(actual_1st_2nd) >= 2
        and pred_top2[0] == actual_1st_2nd[0]
        and pred_top2[1] == actual_1st_2nd[1]
    )

    # 回収率計算用オッズ
    win_odds = odds_map.get(pred_top1, 0.0)
    place_odds_list = [odds_map.get(n, 0.0) for n in pred_nums[:3]]

    return {
        "race_id": race_info["race_id"],
        "race_date": race_info["race_date"],
        "race_name": race_info["race_name"],
        "venue": race_info["venue"],
        "race_number": race_info["race_number"],
        "grade": race_info["grade"],
        "surface": race_info["surface"],
        "distance": race_info["distance"],
        "win_hit": win_hit,
        "place_hit": place_hit,
        "top3_hit": top3_hit,
        "trifecta_hit": trifecta_hit,
        "exacta_hit": exacta_hit,
        "win_odds": win_odds,
        "place_odds_list": place_odds_list,
        "predicted_top3": list(pred_top3),
        "actual_top3": list(actual_top3),
        "honmei_name": ranked[0]["horse_name"] if ranked else "",
        "honmei_number": pred_top1,
        "honmei_actual_pos": honmei_actual_pos,
        "num_runners": len(actual_map),
    }


def compute_summary(results):
    """全レース結果を集計"""
    if not results:
        return {}

    n = len(results)

    # 的中数
    win_hits = sum(1 for r in results if r["win_hit"])
    place_hits = sum(1 for r in results if r["place_hit"])
    trifecta_hits = sum(1 for r in results if r["trifecta_hit"])
    exacta_hits = sum(1 for r in results if r["exacta_hit"])
    total_top3_hits = sum(r["top3_hit"] for r in results)

    # 回収率（単勝: 的中時 オッズ×100円、不的中時 -100円）
    win_payout = sum(r["win_odds"] * 100 if r["win_hit"] else 0 for r in results)
    win_investment = n * 100
    win_roi = (win_payout / win_investment * 100) if win_investment > 0 else 0.0

    # 複勝回収率（概算: 的中時 オッズ÷3×100円）
    place_payout = sum(
        (r["win_odds"] / 3.0) * 100 if r["place_hit"] and r["win_odds"] > 0 else 0
        for r in results
    )
    place_roi = (place_payout / win_investment * 100) if win_investment > 0 else 0.0

    # カテゴリ別集計
    by_venue = _aggregate_by(results, "venue")
    by_grade = _aggregate_by(results, "grade")
    by_surface = _aggregate_by(results, "surface")

    # 日付範囲
    dates = sorted(r["race_date"] for r in results)

    return {
        "win_rate": win_hits / n * 100,
        "place_rate": place_hits / n * 100,
        "show_rate": total_top3_hits / (n * 3) * 100,
        "trifecta_rate": trifecta_hits / n * 100,
        "exacta_rate": exacta_hits / n * 100,
        "win_hits": win_hits,
        "place_hits": place_hits,
        "trifecta_hits": trifecta_hits,
        "exacta_hits": exacta_hits,
        "win_roi": win_roi,
        "place_roi": place_roi,
        "by_venue": by_venue,
        "by_grade": by_grade,
        "by_surface": by_surface,
        "date_range": f"{dates[0]} 〜 {dates[-1]}" if dates else "N/A",
    }


def _aggregate_by(results, key):
    """指定キーでグループ化して勝率・回収率を計算"""
    groups = defaultdict(list)
    for r in results:
        groups[r[key]].append(r)

    summary = {}
    for name, group in sorted(groups.items()):
        g_n = len(group)
        g_win = sum(1 for r in group if r["win_hit"])
        g_place = sum(1 for r in group if r["place_hit"])
        g_payout = sum(r["win_odds"] * 100 if r["win_hit"] else 0 for r in group)
        g_invest = g_n * 100
        summary[name] = {
            "races": g_n,
            "win_rate": g_win / g_n * 100 if g_n > 0 else 0.0,
            "place_rate": g_place / g_n * 100 if g_n > 0 else 0.0,
            "win_roi": g_payout / g_invest * 100 if g_invest > 0 else 0.0,
        }
    return summary
