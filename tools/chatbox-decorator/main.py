"""VRC Chatbox デコレーター — チャットテキストを装飾してVRChatに送信するツール"""

import sys
import os
import time
import argparse
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.osc_client import create_client, send_chatbox, send_typing

# ─── 装飾テンプレート ───

FRAMES = {
    "sparkle": ("✧˖°⌊ ", " ⌉°˖✧"),
    "star": ("★·.·´¯`·.·★ ", " ★·.·´¯`·.·★"),
    "flower": ("✿ ", " ✿"),
    "heart": ("♡ ", " ♡"),
    "music": ("♪♫ ", " ♫♪"),
    "arrow": ("》 ", " 《"),
    "bracket": ("【 ", " 】"),
    "wave": ("〜 ", " 〜"),
    "diamond": ("◆ ", " ◆"),
    "ribbon": ("✦ ", " ✦"),
}

# 特殊文字変換マップ（アルファベット → 装飾文字）
STYLE_MAPS = {
    "bold": str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳",
    ),
    "italic": str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻",
    ),
    "mono": str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣",
    ),
}


def decorate(text: str, frame: str = "sparkle", style: str | None = None) -> str:
    """テキストにフレーム装飾とスタイル変換を適用する"""
    if style and style in STYLE_MAPS:
        text = text.translate(STYLE_MAPS[style])
    prefix, suffix = FRAMES.get(frame, FRAMES["sparkle"])
    return f"{prefix}{text}{suffix}"


def typing_effect(client, text: str, frame: str = "sparkle", delay: float = 0.08):
    """1文字ずつタイピングアニメーションで送信する"""
    prefix, suffix = FRAMES.get(frame, FRAMES["sparkle"])
    send_typing(client, True)
    for i in range(1, len(text) + 1):
        partial = f"{prefix}{text[:i]}▌{suffix}"
        send_chatbox(client, partial)
        time.sleep(delay)
    # 最終表示（カーソルなし）
    send_chatbox(client, f"{prefix}{text}{suffix}")
    send_typing(client, False)


def interactive_mode(client, frame: str, style: str | None, typing: bool, delay: float):
    """対話モード: 入力したテキストを装飾して送信し続ける"""
    print("=" * 50)
    print("  VRC Chatbox デコレーター")
    print("=" * 50)
    print(f"  フレーム: {frame}")
    print(f"  スタイル: {style or 'なし'}")
    print(f"  タイピング演出: {'ON' if typing else 'OFF'}")
    print("=" * 50)
    print("テキストを入力してEnterで送信 (Ctrl+C で終了)")
    print()

    # 利用可能なフレーム一覧を表示
    print("利用可能なフレーム:")
    for name, (pre, suf) in FRAMES.items():
        print(f"  {name:12s} → {pre}サンプル{suf}")
    print()

    try:
        while True:
            text = input(">> ").strip()
            if not text:
                continue

            # コマンド処理
            if text.startswith("/frame "):
                new_frame = text[7:].strip()
                if new_frame in FRAMES:
                    frame = new_frame
                    print(f"フレームを '{frame}' に変更しました")
                else:
                    print(f"不明なフレーム: {new_frame}")
                continue
            if text.startswith("/style "):
                new_style = text[7:].strip()
                if new_style in STYLE_MAPS or new_style == "none":
                    style = None if new_style == "none" else new_style
                    print(f"スタイルを '{style or 'なし'}' に変更しました")
                else:
                    print(f"不明なスタイル: {new_style}")
                continue
            if text == "/typing on":
                typing = True
                print("タイピング演出を ON にしました")
                continue
            if text == "/typing off":
                typing = False
                print("タイピング演出を OFF にしました")
                continue

            if typing:
                # タイピング演出はブロッキングなので別スレッドで実行
                styled = text.translate(STYLE_MAPS[style]) if style and style in STYLE_MAPS else text
                t = threading.Thread(target=typing_effect, args=(client, styled, frame, delay))
                t.start()
                t.join()
            else:
                decorated = decorate(text, frame, style)
                send_chatbox(client, decorated)
                print(f"送信: {decorated}")

    except KeyboardInterrupt:
        print("\n終了します")
        send_typing(client, False)


def main():
    parser = argparse.ArgumentParser(description="VRC Chatbox デコレーター")
    parser.add_argument("--ip", default="127.0.0.1", help="VRChat OSC IP (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9000, help="VRChat OSC Port (default: 9000)")
    parser.add_argument("--frame", default="sparkle", choices=list(FRAMES.keys()), help="装飾フレーム")
    parser.add_argument("--style", choices=list(STYLE_MAPS.keys()), help="文字スタイル変換")
    parser.add_argument("--typing", action="store_true", help="タイピングアニメーション演出を有効にする")
    parser.add_argument("--delay", type=float, default=0.08, help="タイピング速度(秒/文字)")
    parser.add_argument("--send", type=str, help="テキストを1回送信して終了（非対話モード）")
    args = parser.parse_args()

    client = create_client(args.ip, args.port)

    if args.send:
        if args.typing:
            styled = args.send.translate(STYLE_MAPS[args.style]) if args.style else args.send
            typing_effect(client, styled, args.frame, args.delay)
        else:
            decorated = decorate(args.send, args.frame, args.style)
            send_chatbox(client, decorated)
            print(f"送信: {decorated}")
    else:
        interactive_mode(client, args.frame, args.style, args.typing, args.delay)


if __name__ == "__main__":
    main()
