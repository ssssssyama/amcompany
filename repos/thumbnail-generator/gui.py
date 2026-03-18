"""サムネイル生成ツール GUI"""

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
    """generate.py を別コンソールで起動"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate.py")
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
        self.root.title("サムネイル生成")
        self.root.geometry("400x350")
        self.root.resizable(False, False)

        style = ttk.Style()
        style.configure("Title.TLabel", font=("", 14, "bold"))
        style.configure("Desc.TLabel", font=("", 9))
        style.configure("Tool.TButton", font=("", 10), padding=8)

        ttk.Label(self.root, text="サムネイル生成", style="Title.TLabel").pack(pady=(10, 5))
        ttk.Label(self.root, text="BOOTH用620x620pxサムネイルを自動生成", style="Desc.TLabel").pack()

        # タイトル
        title_frame = ttk.LabelFrame(self.root, text="商品タイトル", padding=10)
        title_frame.pack(fill="x", padx=15, pady=3)
        self.title_entry = ttk.Entry(title_frame, width=35)
        self.title_entry.pack(fill="x")

        # サブタイトル
        sub_frame = ttk.LabelFrame(self.root, text="サブタイトル（任意）", padding=10)
        sub_frame.pack(fill="x", padx=15, pady=3)
        self.sub_entry = ttk.Entry(sub_frame, width=35)
        self.sub_entry.pack(fill="x")

        # テーマ
        theme_frame = ttk.LabelFrame(self.root, text="カラーテーマ", padding=10)
        theme_frame.pack(fill="x", padx=15, pady=3)
        self.theme_var = tk.StringVar(value="purple")
        themes = ["purple", "blue", "green", "red", "pink", "orange", "dark", "gold"]
        ttk.Combobox(theme_frame, textvariable=self.theme_var, values=themes, state="readonly", width=15).pack(side="left")

        # ボタン
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="生成", command=self._generate, style="Tool.TButton").pack(side="left", padx=5)
        ttk.Button(btn_frame, text="全商品一括生成", command=self._generate_all).pack(side="left", padx=5)

    def _generate(self):
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showinfo("入力エラー", "商品タイトルを入力してください")
            return
        args = ["--title", title, "--theme", self.theme_var.get()]
        sub = self.sub_entry.get().strip()
        if sub:
            args.extend(["--subtitle", sub])
        run_tool(args)

    def _generate_all(self):
        run_tool(["--all"])

    def run(self):
        self.root.mainloop()


def main():
    if not check_module("PIL"):
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "未インストール",
                "Pillow がインストールされていません。\n\n"
                "setup.bat（Windows）または\n"
                "bash setup.sh（Mac/Linux）を\n"
                "先に実行してください。",
            )
        except Exception:
            print("[エラー] Pillow がインストールされていません。")
            print("  setup.bat または bash setup.sh を実行してください。")
        sys.exit(1)

    app = App()
    app.run()


if __name__ == "__main__":
    main()
