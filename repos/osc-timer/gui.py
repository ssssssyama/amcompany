"""OSCタイマー GUI"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox


def check_module(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def run_tool(args):
    """main.py を別コンソールで起動"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    cmd = [sys.executable, script] + args
    try:
        subprocess.Popen(
            cmd,
            cwd=os.path.dirname(script),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
        )
    except Exception as e:
        messagebox.showerror("起動エラー", f"ツールの起動に失敗しました:\n{e}")


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("OSCタイマー")
        self.root.geometry("350x320")
        self.root.resizable(False, False)

        style = ttk.Style()
        style.configure("Title.TLabel", font=("", 14, "bold"))
        style.configure("Desc.TLabel", font=("", 9))
        style.configure("Tool.TButton", font=("", 10), padding=8)

        ttk.Label(self.root, text="OSCタイマー", style="Title.TLabel").pack(pady=(10, 5))
        ttk.Label(self.root, text="VRChat Chatboxにタイマーを表示", style="Desc.TLabel").pack()

        # モード選択
        self.mode_var = tk.StringVar(value="countdown")
        mode_frame = ttk.LabelFrame(self.root, text="モード", padding=10)
        mode_frame.pack(fill="x", padx=15, pady=5)
        for val, label in [("countdown", "カウントダウン"), ("stopwatch", "ストップウォッチ"), ("pomodoro", "ポモドーロ")]:
            ttk.Radiobutton(mode_frame, text=label, variable=self.mode_var, value=val).pack(anchor="w")

        # 時間設定
        time_frame = ttk.LabelFrame(self.root, text="時間（分）", padding=10)
        time_frame.pack(fill="x", padx=15, pady=5)
        self.minutes_var = tk.StringVar(value="5")
        ttk.Entry(time_frame, textvariable=self.minutes_var, width=10).pack(side="left")
        ttk.Label(time_frame, text="分（カウントダウン用）").pack(side="left", padx=5)

        # 開始ボタン
        ttk.Button(self.root, text="タイマー開始", command=self._start, style="Tool.TButton").pack(pady=15)

    def _start(self):
        mode = self.mode_var.get()
        if mode == "countdown":
            args = ["countdown", self.minutes_var.get()]
        elif mode == "stopwatch":
            args = ["stopwatch"]
        else:
            args = ["pomodoro"]
        run_tool(args)

    def run(self):
        self.root.mainloop()


def main():
    if not check_module("pythonosc"):
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "未インストール",
                "必要なパッケージがインストールされていません。\n\n"
                "setup.bat（Windows）または\n"
                "bash setup.sh（Mac/Linux）を\n"
                "先に実行してください。",
            )
        except Exception:
            print("[エラー] python-osc がインストールされていません。")
            print("  setup.bat または bash setup.sh を実行してください。")
        sys.exit(1)

    app = App()
    app.run()


if __name__ == "__main__":
    main()
