"""Chatbox デコレーター GUI"""

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
        self.root.title("Chatbox デコレーター")
        self.root.geometry("400x380")
        self.root.resizable(False, False)

        style = ttk.Style()
        style.configure("Title.TLabel", font=("", 14, "bold"))
        style.configure("Desc.TLabel", font=("", 9))
        style.configure("Tool.TButton", font=("", 10), padding=8)

        ttk.Label(self.root, text="Chatbox デコレーター", style="Title.TLabel").pack(pady=(10, 5))
        ttk.Label(self.root, text="テキストを装飾してVRChat Chatboxに送信", style="Desc.TLabel").pack()

        # フレーム選択
        self.frame_var = tk.StringVar(value="sparkle")
        frame_frame = ttk.LabelFrame(self.root, text="装飾フレーム", padding=10)
        frame_frame.pack(fill="x", padx=15, pady=5)
        frames = ["sparkle", "star", "flower", "heart", "music", "arrow", "bracket", "wave", "diamond", "ribbon"]
        ttk.Combobox(frame_frame, textvariable=self.frame_var, values=frames, state="readonly", width=15).pack(side="left")

        # スタイル選択
        self.style_var = tk.StringVar(value="none")
        style_frame = ttk.LabelFrame(self.root, text="文字スタイル", padding=10)
        style_frame.pack(fill="x", padx=15, pady=5)
        for s in ["none", "bold", "italic", "mono"]:
            ttk.Radiobutton(style_frame, text=s, variable=self.style_var, value=s).pack(side="left", padx=5)

        # タイピング演出
        self.typing_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.root, text="タイピング演出を有効にする", variable=self.typing_var).pack(padx=15, pady=5, anchor="w")

        # テキスト入力
        text_frame = ttk.LabelFrame(self.root, text="送信テキスト", padding=10)
        text_frame.pack(fill="x", padx=15, pady=5)
        self.text_entry = ttk.Entry(text_frame, width=40)
        self.text_entry.pack(fill="x")

        # ボタン
        ttk.Button(self.root, text="送信", command=self._send, style="Tool.TButton").pack(pady=5)
        ttk.Button(self.root, text="対話モードで起動（別ウィンドウ）", command=self._interactive).pack(pady=3)

    def _build_args(self):
        args = ["--frame", self.frame_var.get()]
        if self.style_var.get() != "none":
            args.extend(["--style", self.style_var.get()])
        if self.typing_var.get():
            args.append("--typing")
        return args

    def _send(self):
        text = self.text_entry.get().strip()
        if not text:
            messagebox.showinfo("入力エラー", "テキストを入力してください")
            return
        args = ["--send", text] + self._build_args()
        run_tool(args)
        self.text_entry.delete(0, tk.END)

    def _interactive(self):
        run_tool(self._build_args())

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
