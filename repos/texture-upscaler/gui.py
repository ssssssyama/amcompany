"""テクスチャ高画質化ツール GUI"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


def check_module(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def run_tool(args):
    """upscale.py を別コンソールで起動"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upscale.py")
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
        self.root.title("テクスチャ高画質化")
        self.root.geometry("420x350")
        self.root.resizable(False, False)

        style = ttk.Style()
        style.configure("Title.TLabel", font=("", 14, "bold"))
        style.configure("Desc.TLabel", font=("", 9))
        style.configure("Tool.TButton", font=("", 10), padding=8)

        ttk.Label(self.root, text="テクスチャ高画質化", style="Title.TLabel").pack(pady=(10, 5))
        ttk.Label(self.root, text="画像をAIで高画質化（4倍アップスケール）", style="Desc.TLabel").pack()

        # ファイル選択
        file_frame = ttk.LabelFrame(self.root, text="画像ファイル / フォルダ", padding=10)
        file_frame.pack(fill="x", padx=15, pady=5)
        self.file_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.file_var, width=30).pack(side="left", fill="x", expand=True)
        btn_f = ttk.Frame(file_frame)
        btn_f.pack(side="left", padx=(5, 0))
        ttk.Button(btn_f, text="ファイル", command=self._browse_file).pack()
        ttk.Button(btn_f, text="フォルダ", command=self._browse_folder).pack(pady=(2, 0))

        # モデル選択
        model_frame = ttk.LabelFrame(self.root, text="モデル", padding=10)
        model_frame.pack(fill="x", padx=15, pady=5)
        self.model_var = tk.StringVar(value="x4plus-anime")
        ttk.Radiobutton(model_frame, text="アニメ調（VRChat推奨）", variable=self.model_var, value="x4plus-anime").pack(anchor="w")
        ttk.Radiobutton(model_frame, text="写実的", variable=self.model_var, value="x4plus").pack(anchor="w")

        # オプション
        opt_frame = ttk.LabelFrame(self.root, text="オプション", padding=10)
        opt_frame.pack(fill="x", padx=15, pady=5)
        self.normal_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="法線マップモード", variable=self.normal_var).pack(anchor="w")

        # 実行ボタン
        ttk.Button(self.root, text="高画質化を実行", command=self._upscale, style="Tool.TButton").pack(pady=10)

    def _browse_file(self):
        f = filedialog.askopenfilename(
            title="高画質化する画像を選択",
            filetypes=[("画像ファイル", "*.png *.jpg *.jpeg *.tga *.bmp *.tiff *.webp"), ("すべて", "*.*")],
        )
        if f:
            self.file_var.set(f)

    def _browse_folder(self):
        d = filedialog.askdirectory(title="画像が入ったフォルダを選択")
        if d:
            self.file_var.set(d)

    def _upscale(self):
        path = self.file_var.get().strip()
        if not path:
            messagebox.showinfo("選択エラー", "画像ファイルまたはフォルダを選択してください")
            return
        args = [path, "--model", self.model_var.get()]
        if self.normal_var.get():
            args.append("--normal-map")
        run_tool(args)

    def run(self):
        self.root.mainloop()


def main():
    if not check_module("realesrgan"):
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "未インストール",
                "AI系パッケージがインストールされていません。\n\n"
                "setup.bat（Windows）または\n"
                "bash setup.sh（Mac/Linux）を\n"
                "先に実行してください。\n\n"
                "GPU（NVIDIA/AMD）が必要です。",
            )
        except Exception:
            print("[エラー] 必要なパッケージがインストールされていません。")
            print("  setup.bat または bash setup.sh を実行してください。")
        sys.exit(1)

    app = App()
    app.run()


if __name__ == "__main__":
    main()
