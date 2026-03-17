"""OSCタイマー＆ストップウォッチ — VRChat Chatboxにタイマーを表示するツール"""

import sys
import os
import time
import argparse
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.osc_client import create_client, send_chatbox, send_parameter
from common.error_handler import friendly_error_handler


def format_time(seconds: int) -> str:
    """秒数を mm:ss または hh:mm:ss 形式にフォーマットする"""
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def countdown(client, minutes: float, label: str, param_name: str | None):
    """カウントダウンタイマー"""
    total_seconds = int(minutes * 60)
    remaining = total_seconds

    print(f"⏱️  カウントダウン開始: {format_time(total_seconds)}")
    print("   Ctrl+C で中断")

    try:
        while remaining >= 0:
            progress = 1.0 - (remaining / total_seconds) if total_seconds > 0 else 1.0
            bar = progress_bar(progress)
            display = f"⏱️ {label} {format_time(remaining)} {bar}"

            send_chatbox(client, display)

            if param_name:
                send_parameter(client, param_name, progress)

            if remaining == 0:
                break
            time.sleep(1)
            remaining -= 1

        # タイマー終了
        finish_msg = f"🔔 {label} 時間です！"
        send_chatbox(client, finish_msg)
        print(f"\n🔔 タイマー終了！")

        if param_name:
            send_parameter(client, param_name, 1.0)

    except KeyboardInterrupt:
        print(f"\n⏹️  タイマー中断 (残り {format_time(remaining)})")
        send_chatbox(client, f"⏹️ {label} 中断")


def stopwatch(client, label: str, param_name: str | None):
    """ストップウォッチ（カウントアップ）"""
    elapsed = 0

    print("⏱️  ストップウォッチ開始")
    print("   Ctrl+C で停止")

    try:
        while True:
            display = f"⏱️ {label} {format_time(elapsed)}"
            send_chatbox(client, display)

            if param_name:
                # 1時間を1.0とするFloat値
                send_parameter(client, param_name, min(elapsed / 3600.0, 1.0))

            time.sleep(1)
            elapsed += 1

    except KeyboardInterrupt:
        final = format_time(elapsed)
        print(f"\n⏹️  停止: {final}")
        send_chatbox(client, f"⏹️ {label} {final}")


def pomodoro(client, work_min: float, break_min: float, cycles: int, param_name: str | None):
    """ポモドーロタイマー（作業→休憩のサイクル）"""
    print(f"🍅 ポモドーロ開始: 作業{work_min:.0f}分 → 休憩{break_min:.0f}分 × {cycles}サイクル")

    try:
        for cycle in range(1, cycles + 1):
            # 作業フェーズ
            print(f"\n--- サイクル {cycle}/{cycles}: 作業 ---")
            work_seconds = int(work_min * 60)
            remaining = work_seconds

            while remaining >= 0:
                progress = 1.0 - (remaining / work_seconds) if work_seconds > 0 else 1.0
                bar = progress_bar(progress)
                display = f"🍅 作業中 [{cycle}/{cycles}] {format_time(remaining)} {bar}"
                send_chatbox(client, display)

                if param_name:
                    send_parameter(client, param_name, progress)

                if remaining == 0:
                    break
                time.sleep(1)
                remaining -= 1

            send_chatbox(client, f"☕ 休憩タイム！ ({break_min:.0f}分)")
            print(f"\n☕ 休憩開始")

            if cycle == cycles:
                send_chatbox(client, "🎉 ポモドーロ完了！お疲れ様！")
                print("🎉 全サイクル完了！")
                break

            # 休憩フェーズ
            break_seconds = int(break_min * 60)
            remaining = break_seconds

            while remaining >= 0:
                progress = 1.0 - (remaining / break_seconds) if break_seconds > 0 else 1.0
                display = f"☕ 休憩中 [{cycle}/{cycles}] {format_time(remaining)}"
                send_chatbox(client, display)

                if remaining == 0:
                    break
                time.sleep(1)
                remaining -= 1

            send_chatbox(client, f"🍅 作業再開！サイクル {cycle + 1}")

    except KeyboardInterrupt:
        print("\n⏹️  ポモドーロ中断")
        send_chatbox(client, "⏹️ ポモドーロ中断")


def progress_bar(ratio: float, width: int = 10) -> str:
    """プログレスバーを生成する"""
    filled = int(ratio * width)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}]"


@friendly_error_handler("OSCタイマー")
def main():
    parser = argparse.ArgumentParser(description="OSCタイマー＆ストップウォッチ")
    parser.add_argument("--ip", default="127.0.0.1", help="VRChat OSC IP")
    parser.add_argument("--port", type=int, default=9000, help="VRChat OSC Port")
    parser.add_argument("--param", default=None, help="進捗をアバターパラメータに送信する名前")
    parser.add_argument("--label", default="", help="タイマーの表示ラベル")

    subparsers = parser.add_subparsers(dest="mode", help="タイマーモード")

    # カウントダウン
    cd_parser = subparsers.add_parser("countdown", help="カウントダウンタイマー")
    cd_parser.add_argument("minutes", type=float, help="カウントダウン時間（分）")

    # ストップウォッチ
    subparsers.add_parser("stopwatch", help="ストップウォッチ（カウントアップ）")

    # ポモドーロ
    pomo_parser = subparsers.add_parser("pomodoro", help="ポモドーロタイマー")
    pomo_parser.add_argument("--work", type=float, default=25, help="作業時間（分、デフォルト25）")
    pomo_parser.add_argument("--break", type=float, default=5, dest="break_min", help="休憩時間（分、デフォルト5）")
    pomo_parser.add_argument("--cycles", type=int, default=4, help="サイクル数（デフォルト4）")

    args = parser.parse_args()

    if not args.mode:
        parser.print_help()
        print("\n使用例:")
        print("  python main.py countdown 5        # 5分カウントダウン")
        print("  python main.py stopwatch           # ストップウォッチ")
        print("  python main.py pomodoro            # ポモドーロ(25分/5分)")
        print('  python main.py countdown 3 --label "ゲーム開始まで"')
        return

    client = create_client(args.ip, args.port)
    label = args.label

    if args.mode == "countdown":
        countdown(client, args.minutes, label or "残り", args.param)
    elif args.mode == "stopwatch":
        stopwatch(client, label or "経過", args.param)
    elif args.mode == "pomodoro":
        pomodoro(client, args.work, args.break_min, args.cycles, args.param)


if __name__ == "__main__":
    main()
