"""結果フォーマッター — 予測結果を見やすく表示"""

from itertools import combinations, permutations


# 印マーク
MARKS = ["◎", "○", "▲", "△", "△", "☆", "☆", "☆"]


def format_ranking(ranked, top_n=5):
    """予想ランキングを文字列に整形"""
    lines = []
    for i, horse in enumerate(ranked[:top_n]):
        mark = MARKS[i] if i < len(MARKS) else "  "
        score = horse["normalized_score"]
        name = horse["horse_name"]
        number = horse["horse_number"]
        jockey = horse["jockey_name"]
        lines.append(f"  {i+1}位: {mark} {number:>2}番 {name:<12} ({jockey}) スコア: {score:.2f}")
    return "\n".join(lines)


def format_tickets(ranked):
    """おすすめ馬券を生成"""
    if len(ranked) < 3:
        return "  出走馬が3頭未満のため馬券予想を生成できません"

    top3 = ranked[:3]
    top2 = ranked[:2]
    n1, n2, n3 = top3[0]["horse_number"], top3[1]["horse_number"], top3[2]["horse_number"]

    lines = []
    # 単勝
    lines.append(f"  【単勝】 {n1}")
    # 複勝
    lines.append(f"  【複勝】 {n1}, {n2}, {n3}")
    # 馬連
    nums = sorted([n1, n2])
    lines.append(f"  【馬連】 {nums[0]}-{nums[1]}")
    # 馬単
    lines.append(f"  【馬単】 {n1}→{n2}")
    # ワイド
    pairs = list(combinations([n1, n2, n3], 2))
    wide_str = ", ".join(f"{sorted(p)[0]}-{sorted(p)[1]}" for p in pairs)
    lines.append(f"  【ワイド】{wide_str}")
    # 三連複
    trio = sorted([n1, n2, n3])
    lines.append(f"  【三連複】{trio[0]}-{trio[1]}-{trio[2]}")
    # 三連単
    lines.append(f"  【三連単】{n1}→{n2}→{n3}")

    # ボックス提案（上位4頭）
    if len(ranked) >= 4:
        top4 = [r["horse_number"] for r in ranked[:4]]
        box_combos = list(combinations(sorted(top4), 3))
        box_str = ", ".join(f"{c[0]}-{c[1]}-{c[2]}" for c in box_combos)
        lines.append(f"  【三連複BOX】{box_str}（上位4頭）")

    return "\n".join(lines)


def format_analysis(ranked, top_n=3):
    """上位馬の分析メモを生成"""
    lines = []
    for horse in ranked[:top_n]:
        feat = horse["features"]
        name = horse["horse_name"]
        notes = []

        # 勝率
        wr = feat.get("horse_win_rate_last5", 0)
        if wr > 0:
            notes.append(f"直近5走勝率{wr:.0%}")

        # 会場実績
        vr = feat.get("venue_win_rate", 0)
        vn = feat.get("venue_races", 0)
        if vn > 0:
            notes.append(f"同会場{vn}走勝率{vr:.0%}")

        # 上がり3F
        l3f = feat.get("avg_last_3f", 0)
        if l3f > 0:
            notes.append(f"上がり3F平均{l3f:.1f}秒")

        # 脚質
        style = feat.get("running_style", "")
        if style and style != "不明":
            notes.append(f"脚質:{style}")

        # 騎手勝率
        jr = feat.get("jockey_win_rate", 0)
        if jr > 0:
            notes.append(f"騎手勝率{jr:.0%}")

        # 休養
        rest = feat.get("rest_days", 0)
        if rest > 0:
            notes.append(f"中{rest}日")

        lines.append(f"  {name}: {', '.join(notes)}")

    return "\n".join(lines)


def format_backtest_results(backtest_result):
    """バックテスト結果を見やすく整形して返す"""
    total = backtest_result["total_races"]
    skipped = backtest_result["skipped_races"]
    method = backtest_result["method"]
    results = backtest_result["results"]
    summary = backtest_result["summary"]

    method_name = "統計モデル" if method == "stat" else "機械学習モデル"

    if not summary:
        return f"\nバックテスト結果なし（対象レースが0件）\n"

    lines = [
        "",
        "=" * 60,
        f"  バックテスト結果 — {method_name}",
        "=" * 60,
        f"  対象: {total}レース（スキップ: {skipped}レース）",
        f"  期間: {summary['date_range']}",
        "",
        "--- 的中率 ---",
        f"  単勝的中率:   {summary['win_rate']:5.1f}%（{summary['win_hits']}/{total}）",
        f"  複勝的中率:   {summary['place_rate']:5.1f}%（{summary['place_hits']}/{total}）— 本命が3着以内",
        f"  三連複的中率: {summary['trifecta_rate']:5.1f}%（{summary['trifecta_hits']}/{total}）",
        f"  馬単的中率:   {summary['exacta_rate']:5.1f}%（{summary['exacta_hits']}/{total}）",
        f"  上位3頭精度: {summary['show_rate']:5.1f}% — 予測3頭中何頭が実際3着以内",
        "",
        "--- 回収率（100円均等買い）---",
        f"  単勝回収率:   {summary['win_roi']:5.1f}%",
        f"  複勝回収率:   {summary['place_roi']:5.1f}%（概算）",
    ]

    # 競馬場別
    if summary.get("by_venue"):
        lines.append("")
        lines.append("--- 競馬場別 ---")
        for name, s in summary["by_venue"].items():
            lines.append(
                f"  {name}: 単勝{s['win_rate']:4.0f}% 複勝{s['place_rate']:4.0f}% "
                f"回収{s['win_roi']:5.0f}%（{s['races']}レース）"
            )

    # グレード別
    if summary.get("by_grade"):
        lines.append("")
        lines.append("--- グレード別 ---")
        for name, s in summary["by_grade"].items():
            lines.append(
                f"  {name}: 単勝{s['win_rate']:4.0f}% 複勝{s['place_rate']:4.0f}% "
                f"回収{s['win_roi']:5.0f}%（{s['races']}レース）"
            )

    # 芝/ダート別
    if summary.get("by_surface"):
        lines.append("")
        lines.append("--- 芝/ダート別 ---")
        for name, s in summary["by_surface"].items():
            lines.append(
                f"  {name}: 単勝{s['win_rate']:4.0f}% 複勝{s['place_rate']:4.0f}% "
                f"回収{s['win_roi']:5.0f}%（{s['races']}レース）"
            )

    # Kelly戦略比較
    if summary.get("kelly_total_bet", 0) > 0:
        lines.append("")
        lines.append("--- 資金配分戦略比較（単勝）---")
        lines.append(
            f"  均等買い（100円/レース）: 回収率{summary['win_roi']:5.1f}%"
        )
        lines.append(
            f"  Kelly戦略（1万円/レース）: 回収率{summary['kelly_roi']:5.1f}% "
            f"（ベット{summary['kelly_bet_count']}レース / 見送り{summary['kelly_skip_count']}レース）"
        )
        lines.append(
            f"  Kelly累計: 投資{summary['kelly_total_bet']:,}円 → "
            f"払戻{summary['kelly_total_payout']:,}円 "
            f"（損益{summary['kelly_total_payout'] - summary['kelly_total_bet']:+,}円）"
        )

    # レース別詳細（直近10レース）
    if results:
        lines.append("")
        lines.append("--- レース別詳細（直近10レース）---")
        recent = sorted(results, key=lambda r: r["race_date"], reverse=True)[:10]
        for r in recent:
            mark = "○" if r["win_hit"] else ("△" if r["place_hit"] else "×")
            odds_str = f"単勝{r['win_odds']:.1f}倍" if r["win_odds"] > 0 else ""
            lines.append(
                f"  {r['race_date']} {r['venue']}{r['race_number']}R {r['race_name']}: "
                f"◎{r['honmei_name']}→{r['honmei_actual_pos']}着 {mark} {odds_str}"
            )

    lines.extend([
        "",
        "=" * 60,
        "  ※ 過去データに対する検証結果であり、将来の成績を保証するものではありません。",
        "=" * 60,
        "",
    ])

    return "\n".join(lines)


def format_allocation(allocation):
    """資金配分の結果を整形"""
    if not allocation:
        return ""

    bets = allocation["bets"]
    total_bet = allocation["total_bet"]
    remaining = allocation["remaining"]
    expected_roi = allocation["expected_roi"]
    strategy = allocation["strategy_note"]
    budget = total_bet + remaining

    lines = [f"--- 資金配分（予算: {budget:,}円）---"]

    if total_bet == 0:
        lines.append(f"  {strategy}")
        lines.append("")
        lines.append("  参考: 上位馬の期待値")
        for b in bets[:5]:
            if not b["has_odds"]:
                lines.append(f"  {b['horse_number']:>2}番 {b['horse_name']:<10} オッズ未取得")
            else:
                edge_pct = b["edge"] * 100
                edge_sign = "+" if edge_pct >= 0 else ""
                lines.append(
                    f"  {b['horse_number']:>2}番 {b['horse_name']:<10} "
                    f"{b['odds']:5.1f}倍  推定勝率{b['win_prob']:.0%}  "
                    f"期待値{edge_sign}{edge_pct:.0f}%"
                )
        return "\n".join(lines)

    for b in bets:
        if not b["has_odds"]:
            lines.append(
                f"  【単勝】{b['horse_number']:>2}番 {b['horse_name']:<10} "
                f"オッズ未取得  → 対象外"
            )
        elif b.get("amount", 0) > 0:
            edge_pct = b["edge"] * 100
            lines.append(
                f"  【単勝】{b['horse_number']:>2}番 {b['horse_name']:<10} "
                f"{b['odds']:5.1f}倍  推定勝率{b['win_prob']:.0%}  "
                f"期待値+{edge_pct:.0f}%  → {b['amount']:,}円"
            )
        else:
            edge_pct = b["edge"] * 100
            edge_sign = "+" if edge_pct >= 0 else ""
            lines.append(
                f"  【単勝】{b['horse_number']:>2}番 {b['horse_name']:<10} "
                f"{b['odds']:5.1f}倍  推定勝率{b['win_prob']:.0%}  "
                f"期待値{edge_sign}{edge_pct:.0f}%  → 見送り"
            )

    lines.append("")
    lines.append(
        f"  合計ベット: {total_bet:,}円 / {budget:,}円  "
        f"期待回収率: {expected_roi:.0f}%"
    )
    lines.append(f"  戦略: {strategy}")

    return "\n".join(lines)


def format_full_prediction(ranked, race_info, top_n=5, method="stat", allocation=None):
    """完全な予想結果を整形して返す"""
    method_name = "統計モデル" if method == "stat" else "機械学習モデル"

    venue = race_info["venue"]
    race_num = race_info["race_number"]
    race_name = race_info["race_name"]
    grade = race_info["grade"]
    distance = race_info["distance"]
    surface = race_info["surface"]
    condition = race_info["track_condition"]

    header = f"{venue}{race_num}R {race_name}（{grade}）{surface}{distance}m {condition}"

    lines = [
        "",
        "=" * 60,
        f"  JRA競馬予想 — {header}",
        "=" * 60,
        f"  予測手法: {method_name}",
        f"  出走頭数: {len(ranked)}頭",
        "",
        "--- 予想ランキング ---",
        format_ranking(ranked, top_n),
        "",
        "--- おすすめ馬券 ---",
        format_tickets(ranked),
    ]

    if allocation:
        lines.append("")
        lines.append(format_allocation(allocation))

    lines.extend([
        "",
        "--- 分析メモ ---",
        format_analysis(ranked, min(top_n, 3)),
        "",
        "=" * 60,
        "  ※ この予想はデータ分析に基づく参考情報です。",
        "  ※ 馬券の購入は自己責任でお願いいたします。",
        "=" * 60,
        "",
    ])

    return "\n".join(lines)
