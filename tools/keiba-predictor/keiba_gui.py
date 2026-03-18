"""JRA競馬予想ツール — GUI版"""

import os
import sys
import re
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_PY = os.path.join(SCRIPT_DIR, "main.py")
DEFAULT_DB = os.path.join(SCRIPT_DIR, "data", "keiba.db")


class KeibaGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("JRA競馬予想ツール")
        self.root.geometry("720x620")
        self.root.minsize(600, 500)
        self._running = False
        self._action_buttons = []

        # DB パス（全タブ共有）
        self.db_var = tk.StringVar(value=DEFAULT_DB)

        # スタイル
        style = ttk.Style()
        style.configure("Title.TLabel", font=("", 14, "bold"))
        style.configure("Run.TButton", font=("", 10), padding=6)

        self._build_tabs()

    # ─────────────────────────────────────────────
    # タブ構築
    # ─────────────────────────────────────────────

    def _build_tabs(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=5, pady=5)

        self._build_predict_tab(nb)
        self._build_fetch_tab(nb)
        self._build_backtest_tab(nb)
        self._build_settings_tab(nb)

    # ── Tab 1: 予想 ──────────────────────────────

    def _build_predict_tab(self, nb):
        tab = ttk.Frame(nb, padding=5)
        nb.add(tab, text=" 予想 ")

        # レース指定
        src_frame = ttk.LabelFrame(tab, text="レース指定", padding=8)
        src_frame.pack(fill="x", padx=5, pady=(5, 3))

        self.predict_mode = tk.StringVar(value="race_id")
        self.race_id_var = tk.StringVar()
        self.csv_var = tk.StringVar()

        # レースID行
        r1 = ttk.Frame(src_frame)
        r1.pack(fill="x", pady=2)
        ttk.Radiobutton(r1, text="レースIDで指定（推奨）", variable=self.predict_mode,
                        value="race_id", command=self._toggle_predict_mode).pack(side="left")
        self.race_id_entry = ttk.Entry(r1, textvariable=self.race_id_var, width=20)
        self.race_id_entry.pack(side="left", padx=(10, 0))

        # CSV行
        r2 = ttk.Frame(src_frame)
        r2.pack(fill="x", pady=2)
        ttk.Radiobutton(r2, text="CSVファイルで指定", variable=self.predict_mode,
                        value="csv", command=self._toggle_predict_mode).pack(side="left")
        self.csv_entry = ttk.Entry(r2, textvariable=self.csv_var, width=25, state="disabled")
        self.csv_entry.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.csv_browse_btn = ttk.Button(r2, text="参照", command=self._browse_csv, state="disabled")
        self.csv_browse_btn.pack(side="left", padx=(3, 0))

        # 予想設定
        opt_frame = ttk.LabelFrame(tab, text="予想設定", padding=8)
        opt_frame.pack(fill="x", padx=5, pady=3)

        r3 = ttk.Frame(opt_frame)
        r3.pack(fill="x", pady=2)
        ttk.Label(r3, text="予測手法:").pack(side="left")
        self.method_var = tk.StringVar(value="stat")
        ttk.Radiobutton(r3, text="統計モデル", variable=self.method_var, value="stat").pack(side="left", padx=(5, 10))
        ttk.Radiobutton(r3, text="機械学習", variable=self.method_var, value="ml").pack(side="left")

        r4 = ttk.Frame(opt_frame)
        r4.pack(fill="x", pady=2)
        ttk.Label(r4, text="予算(円):").pack(side="left")
        self.budget_var = tk.StringVar(value="10000")
        ttk.Entry(r4, textvariable=self.budget_var, width=8).pack(side="left", padx=(5, 15))
        ttk.Label(r4, text="Kelly倍率:").pack(side="left")
        self.kelly_var = tk.StringVar(value="0.5")
        kelly_cb = ttk.Combobox(r4, textvariable=self.kelly_var, values=["0.25", "0.5", "1.0"],
                                width=5, state="readonly")
        kelly_cb.pack(side="left", padx=(5, 15))
        ttk.Label(r4, text="表示頭数:").pack(side="left")
        self.top_var = tk.StringVar(value="5")
        ttk.Entry(r4, textvariable=self.top_var, width=4).pack(side="left", padx=(5, 0))
        ttk.Label(r4, text="頭").pack(side="left")

        # ボタン
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill="x", padx=5, pady=5)
        b1 = ttk.Button(btn_frame, text="予想する", command=self._do_predict, style="Run.TButton")
        b1.pack(side="left", padx=3)
        self._action_buttons.append(b1)
        ttk.Button(btn_frame, text="クリア", command=lambda: self.predict_output.delete("1.0", "end")).pack(side="left", padx=3)

        # 出力エリア
        _, self.predict_output = self._make_output_area(tab)

    def _toggle_predict_mode(self):
        if self.predict_mode.get() == "race_id":
            self.race_id_entry.config(state="normal")
            self.csv_entry.config(state="disabled")
            self.csv_browse_btn.config(state="disabled")
        else:
            self.race_id_entry.config(state="disabled")
            self.csv_entry.config(state="normal")
            self.csv_browse_btn.config(state="normal")

    def _browse_csv(self):
        path = filedialog.askopenfilename(
            title="予測対象CSVを選択",
            filetypes=[("CSVファイル", "*.csv"), ("すべて", "*.*")],
        )
        if path:
            self.csv_var.set(path)

    def _do_predict(self):
        mode = self.predict_mode.get()
        if mode == "race_id":
            rid = self.race_id_var.get().strip()
            if not rid:
                messagebox.showwarning("入力エラー", "レースIDを入力してください")
                return
            src_args = ["--race-id", rid]
        else:
            csv_path = self.csv_var.get().strip()
            if not csv_path:
                sample = os.path.join(SCRIPT_DIR, "sample_data", "upcoming.csv")
                src_args = ["--race", sample]
            else:
                src_args = ["--race", csv_path]

        args = ["predict"] + src_args + [
            "--method", self.method_var.get(),
            "--budget", self.budget_var.get(),
            "--kelly", self.kelly_var.get(),
            "--top", self.top_var.get(),
            "--db", self.db_var.get(),
        ]
        self._run_command(args, self.predict_output)

    # ── Tab 2: データ取得 ────────────────────────

    def _build_fetch_tab(self, nb):
        tab = ttk.Frame(nb, padding=5)
        nb.add(tab, text=" データ取得 ")

        src_frame = ttk.LabelFrame(tab, text="取得方法を選択", padding=8)
        src_frame.pack(fill="x", padx=5, pady=(5, 3))

        self.fetch_mode = tk.StringVar(value="date")
        self.fetch_date_var = tk.StringVar()
        self.fetch_start_var = tk.StringVar()
        self.fetch_end_var = tk.StringVar()
        self.fetch_rid_var = tk.StringVar()
        self.fetch_force_var = tk.BooleanVar(value=False)

        # 日付指定
        r1 = ttk.Frame(src_frame)
        r1.pack(fill="x", pady=2)
        ttk.Radiobutton(r1, text="日付指定", variable=self.fetch_mode, value="date").pack(side="left")
        ttk.Label(r1, text="日付:").pack(side="left", padx=(20, 3))
        ttk.Entry(r1, textvariable=self.fetch_date_var, width=14).pack(side="left")
        ttk.Label(r1, text="(YYYY-MM-DD)").pack(side="left", padx=3)

        # 日付範囲
        r2 = ttk.Frame(src_frame)
        r2.pack(fill="x", pady=2)
        ttk.Radiobutton(r2, text="日付範囲指定", variable=self.fetch_mode, value="range").pack(side="left")
        ttk.Label(r2, text="開始:").pack(side="left", padx=(8, 3))
        ttk.Entry(r2, textvariable=self.fetch_start_var, width=14).pack(side="left")
        ttk.Label(r2, text="終了:").pack(side="left", padx=(8, 3))
        ttk.Entry(r2, textvariable=self.fetch_end_var, width=14).pack(side="left")

        # レースID
        r3 = ttk.Frame(src_frame)
        r3.pack(fill="x", pady=2)
        ttk.Radiobutton(r3, text="レースID指定", variable=self.fetch_mode, value="race_id").pack(side="left")
        ttk.Label(r3, text="ID:").pack(side="left", padx=(16, 3))
        ttk.Entry(r3, textvariable=self.fetch_rid_var, width=18).pack(side="left")

        # force
        r4 = ttk.Frame(src_frame)
        r4.pack(fill="x", pady=2)
        ttk.Checkbutton(r4, text="取得済みデータも再取得する", variable=self.fetch_force_var).pack(side="left", padx=(20, 0))

        # ボタン
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill="x", padx=5, pady=5)
        b1 = ttk.Button(btn_frame, text="取得", command=self._do_fetch, style="Run.TButton")
        b1.pack(side="left", padx=3)
        self._action_buttons.append(b1)
        b2 = ttk.Button(btn_frame, text="レース一覧を表示", command=self._do_list_races)
        b2.pack(side="left", padx=3)
        self._action_buttons.append(b2)
        b3 = ttk.Button(btn_frame, text="データ概要", command=self._do_info)
        b3.pack(side="left", padx=3)
        self._action_buttons.append(b3)

        # 出力エリア
        _, self.fetch_output = self._make_output_area(tab)

    def _validate_date(self, date_str):
        return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', date_str))

    def _do_fetch(self):
        mode = self.fetch_mode.get()
        args = ["fetch"]

        if mode == "date":
            d = self.fetch_date_var.get().strip()
            if not d or not self._validate_date(d):
                messagebox.showwarning("入力エラー", "日付をYYYY-MM-DD形式で入力してください")
                return
            args += ["--date", d]
        elif mode == "range":
            s = self.fetch_start_var.get().strip()
            e = self.fetch_end_var.get().strip()
            if not s or not e or not self._validate_date(s) or not self._validate_date(e):
                messagebox.showwarning("入力エラー", "開始日・終了日をYYYY-MM-DD形式で入力してください")
                return
            args += ["--date-range", s, e]
        else:
            rid = self.fetch_rid_var.get().strip()
            if not rid:
                messagebox.showwarning("入力エラー", "レースIDを入力してください")
                return
            args += ["--race-id", rid]

        if self.fetch_force_var.get():
            args.append("--force")
        args += ["--db", self.db_var.get()]

        self._run_command(args, self.fetch_output)

    def _do_list_races(self):
        d = self.fetch_date_var.get().strip()
        if not d or not self._validate_date(d):
            messagebox.showwarning("入力エラー", "「日付指定」欄に日付をYYYY-MM-DD形式で入力してください")
            return
        self._run_command(["list", "--date", d], self.fetch_output)

    def _do_info(self):
        self._run_command(["info", "--db", self.db_var.get()], self.fetch_output)

    # ── Tab 3: バックテスト ──────────────────────

    def _build_backtest_tab(self, nb):
        tab = ttk.Frame(nb, padding=5)
        nb.add(tab, text=" バックテスト ")

        opt_frame = ttk.LabelFrame(tab, text="バックテスト設定", padding=8)
        opt_frame.pack(fill="x", padx=5, pady=(5, 3))

        r1 = ttk.Frame(opt_frame)
        r1.pack(fill="x", pady=2)
        ttk.Label(r1, text="予測手法:").pack(side="left")
        self.bt_method_var = tk.StringVar(value="stat")
        ttk.Radiobutton(r1, text="統計モデル", variable=self.bt_method_var, value="stat").pack(side="left", padx=(5, 10))
        ttk.Radiobutton(r1, text="機械学習", variable=self.bt_method_var, value="ml").pack(side="left")

        r2 = ttk.Frame(opt_frame)
        r2.pack(fill="x", pady=2)
        ttk.Label(r2, text="最低履歴レース数:").pack(side="left")
        self.min_hist_var = tk.StringVar(value="3")
        ttk.Spinbox(r2, from_=1, to=20, textvariable=self.min_hist_var, width=4).pack(side="left", padx=5)

        # ボタン
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill="x", padx=5, pady=5)
        b1 = ttk.Button(btn_frame, text="実行", command=self._do_backtest, style="Run.TButton")
        b1.pack(side="left", padx=3)
        self._action_buttons.append(b1)
        ttk.Button(btn_frame, text="クリア", command=lambda: self.bt_output.delete("1.0", "end")).pack(side="left", padx=3)

        # 出力
        _, self.bt_output = self._make_output_area(tab)

    def _do_backtest(self):
        args = [
            "backtest",
            "--method", self.bt_method_var.get(),
            "--min-history", self.min_hist_var.get(),
            "--db", self.db_var.get(),
        ]
        self._run_command(args, self.bt_output)

    # ── Tab 4: 設定 ──────────────────────────────

    def _build_settings_tab(self, nb):
        tab = ttk.Frame(nb, padding=5)
        nb.add(tab, text=" 設定 ")

        # DB
        db_frame = ttk.LabelFrame(tab, text="データベース", padding=8)
        db_frame.pack(fill="x", padx=5, pady=(5, 3))
        r1 = ttk.Frame(db_frame)
        r1.pack(fill="x")
        ttk.Label(r1, text="DBパス:").pack(side="left")
        ttk.Entry(r1, textvariable=self.db_var, width=40).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(r1, text="参照", command=self._browse_db).pack(side="left")

        # データ管理
        mgmt_frame = ttk.LabelFrame(tab, text="データ管理", padding=8)
        mgmt_frame.pack(fill="x", padx=5, pady=3)
        mgmt_btns = ttk.Frame(mgmt_frame)
        mgmt_btns.pack(fill="x")
        b1 = ttk.Button(mgmt_btns, text="CSVインポート", command=self._do_import_csv, style="Run.TButton")
        b1.pack(side="left", padx=3)
        self._action_buttons.append(b1)
        b2 = ttk.Button(mgmt_btns, text="MLモデル学習", command=self._do_train, style="Run.TButton")
        b2.pack(side="left", padx=3)
        self._action_buttons.append(b2)

        # 出力
        _, self.settings_output = self._make_output_area(tab)

    def _browse_db(self):
        path = filedialog.askopenfilename(
            title="データベースファイルを選択",
            filetypes=[("SQLiteデータベース", "*.db"), ("すべて", "*.*")],
        )
        if path:
            self.db_var.set(path)

    def _do_import_csv(self):
        path = filedialog.askopenfilename(
            title="インポートするCSVを選択",
            filetypes=[("CSVファイル", "*.csv"), ("すべて", "*.*")],
        )
        if not path:
            return
        self._run_command(["import-csv", "--file", path, "--db", self.db_var.get()], self.settings_output)

    def _do_train(self):
        self._run_command(["train", "--db", self.db_var.get()], self.settings_output)

    # ─────────────────────────────────────────────
    # 共通ユーティリティ
    # ─────────────────────────────────────────────

    def _make_output_area(self, parent):
        """スクロール付きテキスト出力エリアを作成して返す"""
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        text = tk.Text(frame, wrap="none", font=("TkFixedFont", 10),
                       bg="#1e1e1e", fg="#d4d4d4", insertbackground="#d4d4d4",
                       selectbackground="#264f78", relief="flat", borderwidth=1)

        yscroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        text.config(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        return frame, text

    def _run_command(self, args, text_widget):
        """main.pyをサブプロセスで実行し、出力をテキストウィジェットにストリーム表示"""
        if self._running:
            messagebox.showwarning("実行中", "別のコマンドが実行中です。\n完了までお待ちください。")
            return

        self._set_running(True)
        text_widget.delete("1.0", "end")

        def worker():
            try:
                proc = subprocess.Popen(
                    [sys.executable, MAIN_PY] + args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=SCRIPT_DIR,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                for line in proc.stdout:
                    text_widget.after(0, append_line, line)
                proc.wait()
                if proc.returncode != 0:
                    text_widget.after(0, append_line, f"\n[終了コード: {proc.returncode}]\n")
            except Exception as e:
                text_widget.after(0, lambda: messagebox.showerror("エラー", str(e)))
            finally:
                text_widget.after(0, lambda: self._set_running(False))

        def append_line(line):
            text_widget.insert("end", line)
            text_widget.see("end")

        threading.Thread(target=worker, daemon=True).start()

    def _set_running(self, running):
        """実行中フラグに応じてボタンの有効/無効を切り替え"""
        self._running = running
        state = "disabled" if running else "normal"
        for btn in self._action_buttons:
            try:
                btn.config(state=state)
            except tk.TclError:
                pass


def main():
    root = tk.Tk()
    KeibaGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
