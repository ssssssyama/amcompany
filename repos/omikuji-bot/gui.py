"""おみくじBot GUI"""

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
        self.root.title("おみくじBot")
        self.root.geometry("350x280")
        self.root.resizable(False, False)

        style = ttk.Style()
        style.configure("Title.TLabel", font=("", 14, "bold"))
        style.configure("Desc.TLabel", font=("", 9))
        style.configure("Tool.TButton", font=("", 10), padding=8)

        ttk.Label(self.root, text="おみくじBot", style="Title.TLabel").pack(pady=(10, 5))
        ttk.Label(self.root, text="今日の運勢をVRChat Chatboxに表示", style="Desc.TLabel").pack()

        # シード入力
        seed_frame = ttk.LabelFrame(self.root, text="あなたの名前（任意）", padding=10)
        seed_frame.pack(fill="x", padx=15, pady=5)
        self.seed_entry = ttk.Entry(seed_frame, width=30)
        self.seed_entry.pack(fill="x")
        ttk.Label(seed_frame, text="同じ名前なら同じ日は同じ結果になります", style="Desc.TLabel").pack(anchor="w")

        # ドライラン
        self.dry_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.root, text="VRChatに送信せず結果だけ確認する", variable=self.dry_var).pack(padx=15, pady=5, anchor="w")

        # おみくじボタン
        ttk.Button(self.root, text="おみくじを引く！", command=self._draw, style="Tool.TButton").pack(pady=15)

    def _draw(self):
        args = []
        seed = self.seed_entry.get().strip()
        if seed:
            args.extend(["--seed", seed])
        if self.dry_var.get():
            args.append("--dry-run")
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
