"""資金配分最適化エンジン — Kelly Criterionによる最適ベットサイズ計算"""

import math


def scores_to_win_probabilities(ranked, temperature=0.15):
    """予測スコアから各馬の推定勝率に変換（ソフトマックス）

    StatisticalPredictorのスコアは相対値（0.0〜0.6程度）のため、
    温度パラメータ付きソフトマックスで確率空間に写像する。
    温度が低いほど上位馬に確率が集中する。

    Args:
        ranked: predictor.predict() の出力（score降順）
        temperature: ソフトマックス温度（default: 0.15）

    Returns:
        ranked に "win_prob" キーを追加して返す（元リストを変更）
    """
    if not ranked:
        return ranked

    scores = [h["score"] for h in ranked]

    # ソフトマックス with temperature（score / T）
    scaled = [s / temperature for s in scores]
    max_scaled = max(scaled)
    exp_scores = [math.exp(s - max_scaled) for s in scaled]
    total = sum(exp_scores)

    for h, exp_s in zip(ranked, exp_scores):
        h["win_prob"] = exp_s / total if total > 0 else 1.0 / len(ranked)

    return ranked


def compute_kelly(win_prob, odds):
    """1頭分のKelly fractionを計算

    Kelly fraction = (p * b - q) / b
      p = 推定勝率, q = 1 - p, b = odds - 1（純利益倍率）

    Args:
        win_prob: 推定勝率（0〜1）
        odds: 単勝オッズ（例: 3.5）

    Returns:
        float: Kelly fraction（負 = ベットしない方がよい）
    """
    if odds <= 1.0 or win_prob <= 0.0:
        return 0.0

    b = odds - 1.0
    q = 1.0 - win_prob
    kelly = (win_prob * b - q) / b
    return kelly


def optimize_allocation(ranked, upcoming_entries, budget=10000, kelly_fraction=0.5):
    """レース全体の資金配分を最適化

    Args:
        ranked: predictor.predict() の出力
        upcoming_entries: 出馬表（oddsフィールド含む）
        budget: 予算（円）
        kelly_fraction: Kelly倍率（0.5 = Half Kelly推奨）

    Returns:
        dict: bets, total_bet, expected_roi, remaining, strategy_note
    """
    # 勝率を推定
    scores_to_win_probabilities(ranked)

    # 出馬表からオッズを取得
    odds_map = {}
    for e in upcoming_entries:
        num = e.get("horse_number", 0)
        odds_val = 0.0
        try:
            odds_val = float(e.get("odds", 0))
        except (ValueError, TypeError):
            pass
        odds_map[num] = odds_val

    # 各馬のKelly fractionを計算
    candidates = []
    for h in ranked:
        num = h["horse_number"]
        odds = odds_map.get(num, 0.0)
        win_prob = h.get("win_prob", 0.0)
        implied_prob = 1.0 / odds if odds > 1.0 else 0.0

        kelly = compute_kelly(win_prob, odds)
        edge = win_prob - implied_prob

        entry = {
            "ticket_type": "単勝",
            "horse_number": num,
            "horse_name": h["horse_name"],
            "win_prob": win_prob,
            "implied_prob": implied_prob,
            "odds": odds,
            "edge": edge,
            "kelly_raw": kelly,
            "kelly": max(0.0, kelly * kelly_fraction),
            "has_odds": odds > 1.0,
        }
        candidates.append(entry)

    # プラス期待値の馬のみ抽出
    positive_bets = [c for c in candidates if c["kelly"] > 0 and c["has_odds"]]

    if not positive_bets:
        return {
            "bets": candidates[:5],  # 上位5頭は参考表示
            "total_bet": 0,
            "expected_roi": 0.0,
            "remaining": budget,
            "strategy_note": "期待値がプラスの馬が見つかりませんでした。見送り推奨です。",
        }

    # Kelly比率に基づいて金額配分
    total_kelly = sum(b["kelly"] for b in positive_bets)

    # Kelly合計が1を超える場合は正規化（過剰ベット防止）
    if total_kelly > 1.0:
        for b in positive_bets:
            b["kelly"] = b["kelly"] / total_kelly

    for b in positive_bets:
        raw_amount = budget * b["kelly"]
        b["amount"] = max(100, int(raw_amount / 100) * 100)  # 100円単位に切捨て

    # 合計がbudgetを超えないよう調整
    total = sum(b["amount"] for b in positive_bets)
    if total > budget:
        ratio = budget / total
        for b in positive_bets:
            b["amount"] = max(100, int(b["amount"] * ratio / 100) * 100)
        total = sum(b["amount"] for b in positive_bets)

    # 期待回収率を計算
    expected_return = sum(b["win_prob"] * b["odds"] * b["amount"] for b in positive_bets)
    expected_roi = (expected_return / total * 100) if total > 0 else 0.0

    # ベットしない馬も含めた全リスト（参考表示用）
    bet_nums = {b["horse_number"] for b in positive_bets}
    all_bets = []
    for c in candidates[:8]:  # 上位8頭まで
        if c["horse_number"] in bet_nums:
            match = next(b for b in positive_bets if b["horse_number"] == c["horse_number"])
            all_bets.append(match)
        else:
            c["amount"] = 0
            all_bets.append(c)

    kelly_label = {0.25: "Quarter", 0.5: "Half", 1.0: "Full"}.get(kelly_fraction, f"{kelly_fraction:.0%}")

    return {
        "bets": all_bets,
        "total_bet": total,
        "expected_roi": expected_roi,
        "remaining": budget - total,
        "strategy_note": f"期待値プラスの馬に{kelly_label} Kellyで配分（{len(positive_bets)}頭）",
    }


def simulate_kelly_race(ranked, actual_entries, budget=10000, kelly_fraction=0.5):
    """1レース分のKelly戦略シミュレーション（バックテスト用）

    Args:
        ranked: 予測ランキング
        actual_entries: 実際の結果（finish_position, odds含む）
        budget: 1レースあたり予算
        kelly_fraction: Kelly倍率

    Returns:
        dict: bet_amount, payout, profit, bet_count
    """
    allocation = optimize_allocation(ranked, actual_entries, budget, kelly_fraction)

    total_bet = allocation["total_bet"]
    if total_bet == 0:
        return {"bet_amount": 0, "payout": 0, "profit": 0, "bet_count": 0, "skipped": True}

    # 実際の勝ち馬を特定
    winner_num = None
    for e in actual_entries:
        if e.get("finish_position") == 1:
            winner_num = e["horse_number"]
            break

    # 払戻計算
    payout = 0
    bet_count = 0
    for b in allocation["bets"]:
        if b.get("amount", 0) > 0:
            bet_count += 1
            if b["horse_number"] == winner_num and b["odds"] > 0:
                payout += int(b["odds"] * b["amount"])

    return {
        "bet_amount": total_bet,
        "payout": payout,
        "profit": payout - total_bet,
        "bet_count": bet_count,
        "skipped": False,
    }
