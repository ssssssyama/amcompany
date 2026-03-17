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


def format_full_prediction(ranked, race_info, top_n=5, method="stat"):
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
        "",
        "--- 分析メモ ---",
        format_analysis(ranked, min(top_n, 3)),
        "",
        "=" * 60,
        "  ※ この予想はデータ分析に基づく参考情報です。",
        "  ※ 馬券の購入は自己責任でお願いいたします。",
        "=" * 60,
        "",
    ]

    return "\n".join(lines)
