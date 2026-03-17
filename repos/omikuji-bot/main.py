"""今日の運勢おみくじBot — VRChat Chatboxに運勢を表示するツール"""

import random
import hashlib
import argparse
from datetime import date

from lib.osc_client import create_client, send_chatbox, send_parameter
from lib.error_handler import friendly_error_handler

# ─── おみくじデータ ───

FORTUNES = [
    {"rank": "大吉", "emoji": "🌟", "weight": 10},
    {"rank": "吉", "emoji": "☀️", "weight": 20},
    {"rank": "中吉", "emoji": "⛅", "weight": 25},
    {"rank": "小吉", "emoji": "🌤️", "weight": 20},
    {"rank": "末吉", "emoji": "☁️", "weight": 15},
    {"rank": "凶", "emoji": "🌧️", "weight": 8},
    {"rank": "大凶", "emoji": "⛈️", "weight": 2},
]

LUCKY_ITEMS = [
    "コーヒー", "猫耳", "赤いアクセサリー", "お花",
    "音楽", "ミラー", "お菓子", "帽子",
    "マフラー", "星のアクセ", "ぬいぐるみ", "傘",
    "リボン", "メガネ", "手袋", "本",
    "キャンドル", "ペンダント", "指輪", "ブーツ",
]

LUCKY_COLORS = [
    ("赤", 0.0),
    ("オレンジ", 0.08),
    ("黄色", 0.15),
    ("緑", 0.33),
    ("水色", 0.5),
    ("青", 0.6),
    ("紫", 0.75),
    ("ピンク", 0.9),
    ("白", 1.0),
    ("黒", -1.0),
]

ADVICE = [
    "今日は積極的に話しかけてみよう",
    "新しいワールドを探検すると吉",
    "フレンドとの時間を大切に",
    "アバターの模様替えがラッキー",
    "写真を撮ると運気アップ",
    "困っている人を助けると良いことが",
    "ゆっくり休むのも大事な日",
    "新しい出会いがありそう",
    "お気に入りの場所で過ごそう",
    "チャレンジ精神が幸運を呼ぶ",
    "笑顔でいると良いことが起こる",
    "今日の失敗は明日の成功の種",
]


def daily_seed(user_seed: str = "") -> int:
    """日付ベースのシード値を生成（同じ日は同じ結果）"""
    today = date.today().isoformat()
    seed_str = f"{today}:{user_seed}"
    return int(hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16)


def draw_omikuji(user_seed: str = "") -> dict:
    """おみくじを引く"""
    seed = daily_seed(user_seed)
    rng = random.Random(seed)

    # 重み付きランダムで運勢を決定
    weights = [f["weight"] for f in FORTUNES]
    fortune = rng.choices(FORTUNES, weights=weights, k=1)[0]

    lucky_item = rng.choice(LUCKY_ITEMS)
    lucky_color_name, lucky_color_value = rng.choice(LUCKY_COLORS)
    advice = rng.choice(ADVICE)

    # ラッキー度（0.0〜1.0）: 大吉=1.0、大凶=0.0
    rank_index = [f["rank"] for f in FORTUNES].index(fortune["rank"])
    luck_score = 1.0 - (rank_index / (len(FORTUNES) - 1))

    return {
        "rank": fortune["rank"],
        "emoji": fortune["emoji"],
        "lucky_item": lucky_item,
        "lucky_color": lucky_color_name,
        "lucky_color_value": lucky_color_value,
        "advice": advice,
        "luck_score": luck_score,
    }


def format_omikuji(result: dict) -> str:
    """おみくじ結果をChatbox用テキストにフォーマットする"""
    lines = [
        f"⛩️ 今日の運勢: {result['emoji']} {result['rank']} {result['emoji']}",
        f"🍀 ラッキーアイテム: {result['lucky_item']}",
        f"🎨 ラッキーカラー: {result['lucky_color']}",
        f"💬 {result['advice']}",
    ]
    return "\n".join(lines)


@friendly_error_handler("おみくじBot")
def main():
    parser = argparse.ArgumentParser(description="今日の運勢おみくじBot")
    parser.add_argument("--ip", default="127.0.0.1", help="VRChat OSC IP")
    parser.add_argument("--port", type=int, default=9000, help="VRChat OSC Port")
    parser.add_argument("--seed", default="", help="ユーザー固有のシード（名前など）")
    parser.add_argument("--param", default="LuckScore", help="運勢をアバターパラメータに送信する名前")
    parser.add_argument("--no-param", action="store_true", help="アバターパラメータ送信を無効にする")
    parser.add_argument("--dry-run", action="store_true", help="OSC送信せずに結果だけ表示")
    args = parser.parse_args()

    result = draw_omikuji(args.seed)
    text = format_omikuji(result)

    print("=" * 40)
    print(text)
    print("=" * 40)
    print(f"ラッキー度: {result['luck_score']:.0%}")

    if not args.dry_run:
        client = create_client(args.ip, args.port)
        send_chatbox(client, text)
        print("\n✅ Chatboxに送信しました")

        if not args.no_param:
            send_parameter(client, args.param, result["luck_score"])
            print(f"✅ パラメータ '{args.param}' = {result['luck_score']:.2f} を送信しました")
    else:
        print("\n(dry-run: OSC送信はスキップしました)")


if __name__ == "__main__":
    main()
