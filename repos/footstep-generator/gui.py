"""足音AI生成ツール GUI"""

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


SURFACES = [
    ("wood", "木の床"),
    ("stone", "石畳"),
    ("grass", "草地"),
    ("metal", "金属"),
    ("gravel", "砂利"),
    ("snow", "雪"),
    ("water", "水たまり"),
    ("carpet", "カーペット"),
    ("sand", "砂浜"),
    ("tile", "タイル"),
]


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("足音AI生成ツール")
        self.root.geometry("420x520")
        self.root.resizable(False, False)

        style = ttk.Style()
        style.configure("Title.TLabel", font=("", 14, "bold"))
        style.configure("Desc.TLabel", font=("", 9))
        style.configure("Tool.TButton", font=("", 10), padding=8)

        ttk.Label(self.root, text="足音AI生成ツール", style="Title.TLabel").pack(pady=(10, 5))
        ttk.Label(self.root, text="VRChatアバター用の足音効果音をAIで生成", style="Desc.TLabel").pack()

        # サーフェス選択
        surf_frame = ttk.LabelFrame(self.root, text="サーフェス（生成する足音の種類）", padding=10)
        surf_frame.pack(fill="x", padx=15, pady=5)

        self.surface_vars = {}
        for i, (sid, name) in enumerate(SURFACES):
            var = tk.BooleanVar(value=True)
            self.surface_vars[sid] = var
            row, col = divmod(i, 2)
            ttk.Checkbutton(surf_frame, text=f"{name}（{sid}）", variable=var).grid(row=row, column=col, sticky="w", padx=5)

        btn_frame = ttk.Frame(surf_frame)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(5, 0))
        ttk.Button(btn_frame, text="全選択", command=lambda: self._set_all(True)).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="全解除", command=lambda: self._set_all(False)).pack(side="left", padx=3)

        # バリエーション数
        opt_frame = ttk.LabelFrame(self.root, text="オプション", padding=10)
        opt_frame.pack(fill="x", padx=15, pady=5)

        ttk.Label(opt_frame, text="バリエーション数:").grid(row=0, column=0, sticky="w")
        self.var_count = tk.StringVar(value="3")
        ttk.Spinbox(opt_frame, from_=1, to=10, textvariable=self.var_count, width=5).grid(row=0, column=1, padx=5)

        ttk.Label(opt_frame, text="音の長さ（秒）:").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.duration = tk.StringVar(value="0.5")
        ttk.Entry(opt_frame, textvariable=self.duration, width=8).grid(row=1, column=1, padx=5, pady=(5, 0))

        # 出力先
        out_frame = ttk.LabelFrame(self.root, text="出力先", padding=10)
        out_frame.pack(fill="x", padx=15, pady=5)
        self.output_var = tk.StringVar(value="./output")
        ttk.Entry(out_frame, textvariable=self.output_var, width=30).pack(side="left", fill="x", expand=True)
        ttk.Button(out_frame, text="参照", command=self._browse_output).pack(side="left", padx=(5, 0))

        # 生成ボタン
        ttk.Button(self.root, text="生成開始", command=self._generate, style="Tool.TButton").pack(pady=10)

    def _set_all(self, value):
        for var in self.surface_vars.values():
            var.set(value)

    def _browse_output(self):
        d = filedialog.askdirectory()
        if d:
            self.output_var.set(d)

    def _generate(self):
        selected = [sid for sid, var in self.surface_vars.items() if var.get()]
        if not selected:
            messagebox.showinfo("選択エラー", "サーフェスを1つ以上選択してください")
            return

        args = ["--surfaces"] + selected
        args.extend(["--variations", self.var_count.get()])
        args.extend(["--duration", self.duration.get()])
        args.extend(["--output", self.output_var.get()])
        run_tool(args)

    def run(self):
        self.root.mainloop()


def main():
    if not check_module("stable_audio_tools"):
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
