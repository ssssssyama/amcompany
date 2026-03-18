"""AM Company ツールランチャー — GUIで各ツールをかんたんに起動"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")


def check_module(module_name):
    """モジュールがインストール済みか確認"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


def run_tool(script_path, args=None, cwd=None):
    """ツールを別プロセスで起動"""
    cmd = [sys.executable, script_path]
    if args:
        cmd.extend(args)
    try:
        subprocess.Popen(
            cmd,
            cwd=cwd or os.path.dirname(script_path),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
        )
    except Exception as e:
        messagebox.showerror("起動エラー", f"ツールの起動に失敗しました:\n{e}")


class ToolLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AM Company ツールランチャー")
        self.root.geometry("520x620")
        self.root.resizable(False, False)

        # スタイル
        style = ttk.Style()
        style.configure("Title.TLabel", font=("", 16, "bold"))
        style.configure("Section.TLabel", font=("", 12, "bold"))
        style.configure("Desc.TLabel", font=("", 9))
        style.configure("Tool.TButton", font=("", 10), padding=8)

        self._build_ui()

    def _build_ui(self):
        root = self.root

        # タイトル
        title_frame = ttk.Frame(root, padding=15)
        title_frame.pack(fill="x")
        ttk.Label(title_frame, text="AM Company ツールランチャー", style="Title.TLabel").pack()
        ttk.Label(title_frame, text="使いたいツールをクリックしてください", style="Desc.TLabel").pack(pady=(5, 0))

        # セパレータ
        ttk.Separator(root).pack(fill="x", padx=15)

        # スクロール可能なフレーム
        canvas = tk.Canvas(root, highlightthickness=0)
        scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas, padding=15)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # === VRChatツール ===
        self._add_section(scroll_frame, "VRChat ツール（OSC）")
        self._add_tool(
            scroll_frame,
            "Chatbox デコレーター",
            "テキストを装飾フレームで囲んでChatboxに送信",
            self._launch_chatbox_decorator,
        )
        self._add_tool(
            scroll_frame,
            "おみくじBot",
            "今日の運勢をChatboxに表示（日替わり）",
            self._launch_omikuji,
        )
        self._add_tool(
            scroll_frame,
            "OSCタイマー",
            "カウントダウン・ストップウォッチ・ポモドーロ",
            self._launch_timer,
        )

        # === AI系ツール ===
        self._add_section(scroll_frame, "AI系ツール（GPU推奨）")
        self._add_tool(
            scroll_frame,
            "テクスチャ高画質化",
            "画像を選択してAIで高画質化（4倍アップスケール）",
            self._launch_upscaler,
        )
        self._add_tool(
            scroll_frame,
            "足音AI生成",
            "VRChatアバター用の足音効果音をAIで生成",
            self._launch_footstep,
        )

        # === 分析ツール ===
        self._add_section(scroll_frame, "分析ツール")
        self._add_tool(
            scroll_frame,
            "JRA競馬予想",
            "過去データ分析で馬券予想を生成",
            self._launch_keiba,
        )

        # === その他 ===
        self._add_section(scroll_frame, "その他")
        self._add_tool(
            scroll_frame,
            "サムネイル生成",
            "BOOTH用620x620pxサムネイルを自動生成",
            self._launch_thumbnail,
        )

        # ステータスバー
        status_frame = ttk.Frame(root, padding=(15, 5))
        status_frame.pack(fill="x", side="bottom")
        self.status_label = ttk.Label(status_frame, text="", style="Desc.TLabel")
        self.status_label.pack(side="left")

        # 依存チェック
        self._check_dependencies()

    def _add_section(self, parent, title):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=(15, 5))
        ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor="w")
        ttk.Separator(frame).pack(fill="x", pady=(3, 0))

    def _add_tool(self, parent, name, description, command):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=3)
        btn = ttk.Button(frame, text=name, style="Tool.TButton", command=command, width=20)
        btn.pack(side="left", padx=(0, 10))
        ttk.Label(frame, text=description, style="Desc.TLabel", wraplength=250).pack(side="left", fill="x")

    def _check_dependencies(self):
        missing = []
        if not check_module("pythonosc"):
            missing.append("python-osc（VRChatツール用）")
        if not check_module("PIL"):
            missing.append("Pillow（画像処理用）")
        if missing:
            self.status_label.config(
                text=f"未インストール: {', '.join(missing)} → setup.bat を実行してください",
                foreground="red",
            )
        else:
            self.status_label.config(text="全ての基本パッケージがインストール済みです", foreground="green")

    # === ツール起動関数 ===

    def _launch_chatbox_decorator(self):
        if not check_module("pythonosc"):
            messagebox.showwarning("未インストール", "python-osc がインストールされていません。\nsetup.bat を実行してください。")
            return
        self._open_chatbox_window()

    def _open_chatbox_window(self):
        win = tk.Toplevel(self.root)
        win.title("Chatbox デコレーター")
        win.geometry("400x350")
        win.resizable(False, False)

        ttk.Label(win, text="Chatbox デコレーター", style="Section.TLabel").pack(pady=(10, 5))

        # フレーム選択
        frame_var = tk.StringVar(value="sparkle")
        frame_frame = ttk.LabelFrame(win, text="装飾フレーム", padding=10)
        frame_frame.pack(fill="x", padx=15, pady=5)

        frames = ["sparkle", "star", "flower", "heart", "music", "arrow", "bracket", "wave", "diamond", "ribbon"]
        frame_combo = ttk.Combobox(frame_frame, textvariable=frame_var, values=frames, state="readonly", width=15)
        frame_combo.pack(side="left")

        # スタイル選択
        style_var = tk.StringVar(value="none")
        style_frame = ttk.LabelFrame(win, text="文字スタイル", padding=10)
        style_frame.pack(fill="x", padx=15, pady=5)

        for s in ["none", "bold", "italic", "mono"]:
            ttk.Radiobutton(style_frame, text=s, variable=style_var, value=s).pack(side="left", padx=5)

        # タイピング演出
        typing_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(win, text="タイピング演出を有効にする", variable=typing_var).pack(padx=15, pady=5, anchor="w")

        # テキスト入力
        text_frame = ttk.LabelFrame(win, text="送信テキスト", padding=10)
        text_frame.pack(fill="x", padx=15, pady=5)
        text_entry = ttk.Entry(text_frame, width=40)
        text_entry.pack(fill="x")

        def send():
            text = text_entry.get().strip()
            if not text:
                messagebox.showinfo("入力エラー", "テキストを入力してください")
                return
            args = ["--send", text, "--frame", frame_var.get()]
            if style_var.get() != "none":
                args.extend(["--style", style_var.get()])
            if typing_var.get():
                args.append("--typing")
            script = os.path.join(TOOLS_DIR, "chatbox-decorator", "main.py")
            run_tool(script, args)
            text_entry.delete(0, tk.END)

        # 送信ボタン
        ttk.Button(win, text="送信", command=send, style="Tool.TButton").pack(pady=10)

        # 対話モードボタン
        def interactive():
            script = os.path.join(TOOLS_DIR, "chatbox-decorator", "main.py")
            args = ["--frame", frame_var.get()]
            if style_var.get() != "none":
                args.extend(["--style", style_var.get()])
            if typing_var.get():
                args.append("--typing")
            run_tool(script, args)

        ttk.Button(win, text="対話モードで起動（別ウィンドウ）", command=interactive).pack()

    def _launch_omikuji(self):
        if not check_module("pythonosc"):
            messagebox.showwarning("未インストール", "python-osc がインストールされていません。\nsetup.bat を実行してください。")
            return
        self._open_omikuji_window()

    def _open_omikuji_window(self):
        win = tk.Toplevel(self.root)
        win.title("おみくじBot")
        win.geometry("350x250")
        win.resizable(False, False)

        ttk.Label(win, text="おみくじBot", style="Section.TLabel").pack(pady=(10, 5))

        # シード入力
        seed_frame = ttk.LabelFrame(win, text="あなたの名前（任意）", padding=10)
        seed_frame.pack(fill="x", padx=15, pady=5)
        seed_entry = ttk.Entry(seed_frame, width=30)
        seed_entry.pack(fill="x")
        ttk.Label(seed_frame, text="同じ名前なら同じ日は同じ結果になります", style="Desc.TLabel").pack(anchor="w")

        # ドライラン
        dry_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(win, text="VRChatに送信せず結果だけ確認する", variable=dry_var).pack(padx=15, pady=5, anchor="w")

        def draw():
            script = os.path.join(TOOLS_DIR, "omikuji-bot", "main.py")
            args = []
            seed = seed_entry.get().strip()
            if seed:
                args.extend(["--seed", seed])
            if dry_var.get():
                args.append("--dry-run")
            run_tool(script, args)

        ttk.Button(win, text="おみくじを引く！", command=draw, style="Tool.TButton").pack(pady=15)

    def _launch_timer(self):
        if not check_module("pythonosc"):
            messagebox.showwarning("未インストール", "python-osc がインストールされていません。\nsetup.bat を実行してください。")
            return
        self._open_timer_window()

    def _open_timer_window(self):
        win = tk.Toplevel(self.root)
        win.title("OSCタイマー")
        win.geometry("350x300")
        win.resizable(False, False)

        ttk.Label(win, text="OSCタイマー", style="Section.TLabel").pack(pady=(10, 5))

        # モード選択
        mode_var = tk.StringVar(value="countdown")
        mode_frame = ttk.LabelFrame(win, text="モード", padding=10)
        mode_frame.pack(fill="x", padx=15, pady=5)
        for val, label in [("countdown", "カウントダウン"), ("stopwatch", "ストップウォッチ"), ("pomodoro", "ポモドーロ")]:
            ttk.Radiobutton(mode_frame, text=label, variable=mode_var, value=val).pack(anchor="w")

        # 時間設定
        time_frame = ttk.LabelFrame(win, text="時間（分）※カウントダウン用", padding=10)
        time_frame.pack(fill="x", padx=15, pady=5)
        minutes_var = tk.StringVar(value="5")
        ttk.Entry(time_frame, textvariable=minutes_var, width=10).pack(side="left")
        ttk.Label(time_frame, text="分").pack(side="left", padx=5)

        def start():
            script = os.path.join(TOOLS_DIR, "osc-timer", "main.py")
            mode = mode_var.get()
            if mode == "countdown":
                args = ["countdown", minutes_var.get()]
            elif mode == "stopwatch":
                args = ["stopwatch"]
            else:
                args = ["pomodoro"]
            run_tool(script, args)

        ttk.Button(win, text="タイマー開始", command=start, style="Tool.TButton").pack(pady=15)

    def _launch_upscaler(self):
        if not check_module("realesrgan"):
            messagebox.showwarning(
                "未インストール",
                "テクスチャ高画質化ツールの依存パッケージがインストールされていません。\n\n"
                "以下のコマンドを実行してください:\n"
                "pip install -r requirements-upscaler.txt",
            )
            return

        filepath = filedialog.askopenfilename(
            title="高画質化する画像を選択",
            filetypes=[("画像ファイル", "*.png *.jpg *.jpeg *.tga *.bmp *.tiff *.webp"), ("すべて", "*.*")],
        )
        if filepath:
            script = os.path.join(TOOLS_DIR, "texture-upscaler", "upscale.py")
            run_tool(script, [filepath])

    def _launch_footstep(self):
        if not check_module("stable_audio_tools"):
            messagebox.showwarning(
                "未インストール",
                "足音生成ツールの依存パッケージがインストールされていません。\n\n"
                "以下のコマンドを実行してください:\n"
                "pip install -r requirements-footstep.txt",
            )
            return
        script = os.path.join(TOOLS_DIR, "footstep-generator", "generate.py")
        run_tool(script)

    def _launch_keiba(self):
        gui_script = os.path.join(TOOLS_DIR, "keiba-predictor", "keiba_gui.py")
        subprocess.Popen(
            [sys.executable, gui_script],
            cwd=os.path.join(TOOLS_DIR, "keiba-predictor"),
        )

    def _launch_thumbnail(self):
        if not check_module("PIL"):
            messagebox.showwarning("未インストール", "Pillow がインストールされていません。\nsetup.bat を実行してください。")
            return
        self._open_thumbnail_window()

    def _open_thumbnail_window(self):
        win = tk.Toplevel(self.root)
        win.title("サムネイル生成")
        win.geometry("400x350")
        win.resizable(False, False)

        ttk.Label(win, text="サムネイル生成", style="Section.TLabel").pack(pady=(10, 5))

        # タイトル
        title_frame = ttk.LabelFrame(win, text="商品タイトル", padding=10)
        title_frame.pack(fill="x", padx=15, pady=3)
        title_entry = ttk.Entry(title_frame, width=35)
        title_entry.pack(fill="x")

        # サブタイトル
        sub_frame = ttk.LabelFrame(win, text="サブタイトル（任意）", padding=10)
        sub_frame.pack(fill="x", padx=15, pady=3)
        sub_entry = ttk.Entry(sub_frame, width=35)
        sub_entry.pack(fill="x")

        # テーマ
        theme_var = tk.StringVar(value="purple")
        theme_frame = ttk.LabelFrame(win, text="カラーテーマ", padding=10)
        theme_frame.pack(fill="x", padx=15, pady=3)
        themes = ["purple", "blue", "green", "red", "pink", "orange", "dark", "gold"]
        ttk.Combobox(theme_frame, textvariable=theme_var, values=themes, state="readonly", width=15).pack(side="left")

        def generate():
            title = title_entry.get().strip()
            if not title:
                messagebox.showinfo("入力エラー", "商品タイトルを入力してください")
                return
            script = os.path.join(TOOLS_DIR, "thumbnail-generator", "generate.py")
            args = ["--title", title, "--theme", theme_var.get()]
            sub = sub_entry.get().strip()
            if sub:
                args.extend(["--subtitle", sub])
            run_tool(script, args)

        def generate_all():
            script = os.path.join(TOOLS_DIR, "thumbnail-generator", "generate.py")
            run_tool(script, ["--all"])

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="生成", command=generate, style="Tool.TButton").pack(side="left", padx=5)
        ttk.Button(btn_frame, text="全商品一括生成", command=generate_all).pack(side="left", padx=5)

    def run(self):
        self.root.mainloop()


def main():
    try:
        app = ToolLauncher()
        app.run()
    except Exception as e:
        print(f"[エラー] GUIの起動に失敗しました: {e}")
        print("")
        print("Tkinterがインストールされていない可能性があります。")
        print("  Linux: sudo apt install python3-tk")
        print("  Mac:   brew install python-tk")
        print("")
        print("GUIなしで各ツールを直接起動することもできます。")
        print("詳しくはREADME.mdを参照してください。")
        sys.exit(1)


if __name__ == "__main__":
    main()
