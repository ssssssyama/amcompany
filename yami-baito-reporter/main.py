"""闇バイト通報支援ツール — メインGUIアプリケーション"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser

# 同ディレクトリからインポート
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import CHECKLIST_ITEMS, REPORTING_CHANNELS, REWARD_INFO, RISK_LEVELS
import report_logger


class YamiBaitoReporter:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("闇バイト通報支援ツール")
        self.root.geometry("620x720")
        self.root.resizable(False, False)

        # スタイル設定
        style = ttk.Style()
        style.configure("Title.TLabel", font=("", 16, "bold"))
        style.configure("Section.TLabel", font=("", 12, "bold"))
        style.configure("Desc.TLabel", font=("", 9))
        style.configure("Risk.TLabel", font=("", 14, "bold"))
        style.configure("Tool.TButton", font=("", 10), padding=8)
        style.configure("Channel.TButton", font=("", 9), padding=4)

        self.check_vars = {}  # チェックボックスの状態
        self._build_ui()

    def _build_ui(self):
        root = self.root

        # タイトル
        title_frame = ttk.Frame(root, padding=10)
        title_frame.pack(fill="x")
        ttk.Label(title_frame, text="闇バイト通報支援ツール", style="Title.TLabel").pack()
        ttk.Label(
            title_frame,
            text="怪しい求人の危険度チェック & 通報先ガイド",
            style="Desc.TLabel",
        ).pack(pady=(3, 0))

        ttk.Separator(root).pack(fill="x", padx=10)

        # タブ
        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=10, pady=5)

        self._build_checklist_tab(notebook)
        self._build_channels_tab(notebook)
        self._build_reward_tab(notebook)

        # フッター
        footer = ttk.Frame(root, padding=(10, 5))
        footer.pack(fill="x", side="bottom")
        ttk.Button(footer, text="過去の記録を見る", command=self._show_history).pack(side="left")
        ttk.Label(
            footer,
            text="※ 虚偽通報は犯罪です。合法的な通報活動にご利用ください。",
            style="Desc.TLabel",
            foreground="#DC143C",
        ).pack(side="right")

    # ========== タブ1: チェックリスト ==========

    def _build_checklist_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="危険度チェック")

        ttk.Label(
            tab,
            text="この求人、大丈夫？",
            style="Section.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            tab,
            text="当てはまる項目にチェックを入れてください",
            style="Desc.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        # スクロール可能なチェックリスト
        canvas = tk.Canvas(tab, highlightthickness=0, height=300)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        check_frame = ttk.Frame(canvas)

        check_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=check_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for item in CHECKLIST_ITEMS:
            var = tk.BooleanVar(value=False)
            self.check_vars[item["id"]] = var

            frame = ttk.Frame(check_frame)
            frame.pack(fill="x", pady=2)

            severity_color = {"high": "#DC143C", "medium": "#FFA500", "low": "#228B22"}
            indicator = tk.Label(
                frame,
                text="\u25cf",
                fg=severity_color.get(item["severity"], "#666"),
                font=("", 8),
            )
            indicator.pack(side="left", padx=(0, 4))

            cb = ttk.Checkbutton(frame, text=item["label"], variable=var)
            cb.pack(side="left", anchor="w")

        # URL入力
        url_frame = ttk.Frame(tab)
        url_frame.pack(fill="x", pady=(8, 3))
        ttk.Label(url_frame, text="求人のURL（任意）:", style="Desc.TLabel").pack(side="left")
        self.url_entry = ttk.Entry(url_frame, width=45)
        self.url_entry.pack(side="left", padx=(5, 0))

        # メモ入力
        notes_frame = ttk.Frame(tab)
        notes_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(notes_frame, text="メモ（任意）:", style="Desc.TLabel").pack(side="left", anchor="n")
        self.notes_entry = tk.Text(notes_frame, height=2, width=45, font=("", 9))
        self.notes_entry.pack(side="left", padx=(5, 0))

        # 判定ボタン
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(
            btn_frame,
            text="危険度を判定する",
            command=self._evaluate_risk,
            style="Tool.TButton",
        ).pack(side="left", padx=(0, 10))
        ttk.Button(
            btn_frame,
            text="結果を保存する",
            command=self._save_report,
        ).pack(side="left")

        # 結果表示エリア
        self.result_frame = ttk.LabelFrame(tab, text="判定結果", padding=10)
        self.result_frame.pack(fill="x", pady=(5, 0))
        self.result_label = tk.Label(
            self.result_frame,
            text="上のチェックリストにチェックを入れて「危険度を判定する」を押してください",
            font=("", 10),
            wraplength=550,
            justify="left",
        )
        self.result_label.pack(fill="x")

        self._current_risk_level = None

    def _evaluate_risk(self):
        checked = self._get_checked_items()
        high_count = sum(
            1
            for item in CHECKLIST_ITEMS
            if item["id"] in checked and item["severity"] == "high"
        )
        total_count = len(checked)

        # リスクレベル判定
        result = RISK_LEVELS[-1]  # デフォルト: 低リスク
        for level in RISK_LEVELS:
            if high_count >= level["min_high"] and total_count >= level["min_total"]:
                result = level
                break

        self._current_risk_level = result["level"]

        # 結果表示
        self.result_label.config(
            text=f"【{result['level']}】\n\n"
            f"チェック数: {total_count}項目（うち高危険: {high_count}項目）\n\n"
            f"{result['message']}",
            fg=result["color"],
        )

    def _get_checked_items(self):
        return [item_id for item_id, var in self.check_vars.items() if var.get()]

    def _save_report(self):
        checked = self._get_checked_items()
        if not checked:
            messagebox.showinfo("保存", "チェック項目がありません。先に危険度チェックを行ってください。")
            return

        if self._current_risk_level is None:
            self._evaluate_risk()

        source_url = self.url_entry.get().strip()
        notes = self.notes_entry.get("1.0", "end").strip()

        filepath = report_logger.save_report(
            checked_ids=checked,
            risk_level=self._current_risk_level,
            source_url=source_url,
            notes=notes,
        )
        messagebox.showinfo("保存完了", f"記録を保存しました:\n{os.path.basename(filepath)}")

    # ========== タブ2: 通報先ガイド ==========

    def _build_channels_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="通報先ガイド")

        # スクロール可能
        canvas = tk.Canvas(tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=5)

        content.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        ttk.Label(content, text="通報・相談先一覧", style="Section.TLabel").pack(
            anchor="w", pady=(0, 8)
        )

        for ch in REPORTING_CHANNELS:
            card = ttk.LabelFrame(content, text=ch["name"], padding=8)
            card.pack(fill="x", pady=4)

            info_frame = ttk.Frame(card)
            info_frame.pack(fill="x")

            ttk.Label(info_frame, text=ch["description"], wraplength=450, style="Desc.TLabel").pack(
                anchor="w"
            )
            ttk.Label(
                info_frame,
                text=f"利用場面: {ch['when_to_use']}",
                wraplength=450,
                style="Desc.TLabel",
                foreground="#555",
            ).pack(anchor="w", pady=(2, 5))

            btn_frame = ttk.Frame(card)
            btn_frame.pack(fill="x")

            if ch["contact_type"] == "url":
                url = ch["contact"]
                ttk.Button(
                    btn_frame,
                    text=f"サイトを開く: {ch['contact']}",
                    command=lambda u=url: webbrowser.open(u),
                    style="Channel.TButton",
                ).pack(side="left")
            else:
                phone = ch["contact"]
                ttk.Label(btn_frame, text=f"電話番号: {phone}", font=("", 11, "bold")).pack(
                    side="left"
                )
                ttk.Button(
                    btn_frame,
                    text="番号をコピー",
                    command=lambda p=phone: self._copy_to_clipboard(p),
                    style="Channel.TButton",
                ).pack(side="left", padx=(10, 0))

        # 通報の流れ
        ttk.Separator(content).pack(fill="x", pady=10)
        ttk.Label(content, text="通報の流れ", style="Section.TLabel").pack(anchor="w", pady=(0, 5))

        steps = [
            "1. チェックリストで危険度を確認する",
            "2. 証拠を保存する（スクリーンショット・URL・やり取りの記録など）",
            "3. 該当する通報窓口に連絡する",
            "4. 知っている情報をできるだけ詳しく伝える",
            "5. 通報内容を記録しておく（本ツールの保存機能も活用できます）",
        ]
        for step in steps:
            ttk.Label(content, text=step, wraplength=500, style="Desc.TLabel").pack(
                anchor="w", pady=1
            )

        ttk.Label(
            content,
            text="\nあなたの通報が誰かを救います。",
            font=("", 10, "bold"),
            foreground="#1E90FF",
        ).pack(anchor="w", pady=(5, 0))

    def _copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("コピー完了", f"「{text}」をクリップボードにコピーしました")

    # ========== タブ3: 報奨金について ==========

    def _build_reward_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="報奨金について")

        canvas = tk.Canvas(tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=5)

        content.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 報奨金制度
        ttk.Label(content, text=REWARD_INFO["title"], style="Section.TLabel").pack(
            anchor="w", pady=(0, 8)
        )

        desc_label = ttk.Label(
            content, text=REWARD_INFO["description"], wraplength=530, style="Desc.TLabel"
        )
        desc_label.pack(anchor="w", pady=(0, 10))

        # 条件
        cond_frame = ttk.LabelFrame(content, text="制度の概要", padding=8)
        cond_frame.pack(fill="x", pady=5)
        for cond in REWARD_INFO["conditions"]:
            ttk.Label(cond_frame, text=f"  {cond}", wraplength=500, style="Desc.TLabel").pack(
                anchor="w", pady=1
            )

        # 利用方法
        how_frame = ttk.LabelFrame(content, text="通報の手順", padding=8)
        how_frame.pack(fill="x", pady=5)
        for i, step in enumerate(REWARD_INFO["how_to"], 1):
            ttk.Label(how_frame, text=f"  {i}. {step}", wraplength=500, style="Desc.TLabel").pack(
                anchor="w", pady=1
            )

        # Webサイトリンク
        btn_frame = ttk.Frame(content)
        btn_frame.pack(fill="x", pady=8)
        ttk.Button(
            btn_frame,
            text="匿名通報ダイヤル公式サイトを開く",
            command=lambda: webbrowser.open(REWARD_INFO["web_url"]),
            style="Tool.TButton",
        ).pack(side="left")

        # 注意事項
        ttk.Separator(content).pack(fill="x", pady=10)
        ttk.Label(content, text="注意事項", style="Section.TLabel").pack(anchor="w", pady=(0, 5))

        disclaimer = tk.Label(
            content,
            text=REWARD_INFO["disclaimer"],
            wraplength=530,
            justify="left",
            fg="#DC143C",
            font=("", 9),
        )
        disclaimer.pack(anchor="w")

        # その他の社会貢献
        ttk.Separator(content).pack(fill="x", pady=10)
        ttk.Label(content, text="その他の啓発活動について", style="Section.TLabel").pack(
            anchor="w", pady=(0, 5)
        )
        ttk.Label(
            content,
            text=(
                "闇バイトの危険性を広く伝えることも重要な社会貢献です。\n"
                "ブログやSNSでの注意喚起、地域の防犯活動への参加など、\n"
                "できることから始めてみてください。"
            ),
            wraplength=530,
            style="Desc.TLabel",
        ).pack(anchor="w")

    # ========== 履歴表示 ==========

    def _show_history(self):
        reports = report_logger.load_reports()

        win = tk.Toplevel(self.root)
        win.title("通報記録の履歴")
        win.geometry("500x400")

        if not reports:
            ttk.Label(win, text="保存された記録はありません", padding=20).pack()
            return

        canvas = tk.Canvas(win, highlightthickness=0)
        scrollbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=10)

        content.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for r in reports:
            frame = ttk.LabelFrame(content, text=r.get("timestamp", "不明"), padding=5)
            frame.pack(fill="x", pady=3)

            risk = r.get("risk_level", "不明")
            count = len(r.get("checked_items", []))
            ttk.Label(frame, text=f"判定: {risk}  |  チェック数: {count}").pack(anchor="w")

            url = r.get("source_url", "")
            if url:
                ttk.Label(frame, text=f"URL: {url}", style="Desc.TLabel").pack(anchor="w")

            notes = r.get("notes", "")
            if notes:
                ttk.Label(
                    frame, text=f"メモ: {notes}", style="Desc.TLabel", wraplength=440
                ).pack(anchor="w")

    def run(self):
        self.root.mainloop()


def main():
    try:
        app = YamiBaitoReporter()
        app.run()
    except Exception as e:
        print(f"[エラー] GUIの起動に失敗しました: {e}")
        print("")
        print("Tkinterがインストールされていない可能性があります。")
        print("  Linux: sudo apt install python3-tk")
        print("  Mac:   brew install python-tk")
        sys.exit(1)


if __name__ == "__main__":
    main()
