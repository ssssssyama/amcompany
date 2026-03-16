"""YAML テスト定義 → Excel テスト仕様書 生成ツール.

YAMLファイルでテストケースを定義し、Excel仕様書に変換する。
Excelを手書きする代わりにYAMLで記述でき、Git差分やIDEの補完が使える。

使い方:
    python gen_spec.py test_spec.yaml -o spec.xlsx
    python gen_spec.py test_spec.yaml              # → test_spec.xlsx に出力
"""

import argparse
import sys
from pathlib import Path

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

# スタイル定数
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_FONT = Font(name="Yu Gothic", size=10, bold=True, color="FFFFFF")
CELL_FONT = Font(name="Yu Gothic", size=10)
THIN_BORDER = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)

VALID_ACTIONS = {
    "navigate", "click", "input", "select", "wait", "wait_for",
    "upload", "hover", "scroll", "keyboard",
    "alert_accept", "alert_dismiss", "iframe", "include", "skip", "",
}
VALID_VERIFY_TYPES = {
    "text", "value", "visible", "hidden", "url", "screenshot", "db", "",
}


def create_sheet(wb, sheet_name, test_cases, project_name="", is_first=False):
    """Excelシートにテストケースを書き込む."""
    if is_first:
        ws = wb.active
        ws.title = sheet_name
    else:
        ws = wb.create_sheet(sheet_name)

    ws["A1"] = "テスト仕様書"
    ws["A1"].font = Font(name="Yu Gothic", size=14, bold=True)
    ws["A2"] = "プロジェクト名:"
    ws["B2"] = project_name
    ws["A3"] = "テスト日:"
    ws["A4"] = "テスト担当者:"
    ws["B4"] = "自動テスト"

    headers = [
        ("A", "No.", 6), ("B", "テスト項目", 30), ("C", "操作種別", 12),
        ("D", "対象セレクタ", 30), ("E", "入力値", 25),
        ("F", "検証種別", 12), ("G", "検証対象", 35),
        ("H", "期待値", 30), ("I", "結果", 8),
        ("J", "エビデンス", 30), ("K", "備考", 25),
    ]
    for col, title, width in headers:
        cell = ws[f"{col}6"]
        cell.value = title
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = THIN_BORDER
        ws.column_dimensions[col].width = width

    for i, tc in enumerate(test_cases):
        row = 7 + i
        values = [
            tc.get("no", i + 1), tc.get("item", ""),
            tc.get("action", ""), tc.get("selector", ""),
            tc.get("input", ""), tc.get("verify_type", ""),
            tc.get("verify_target", ""), tc.get("expected", ""),
            "", "", tc.get("note", ""),
        ]
        for j, val in enumerate(values):
            col = chr(65 + j)
            cell = ws[f"{col}{row}"]
            cell.value = val
            cell.font = CELL_FONT
            cell.border = THIN_BORDER
            cell.alignment = LEFT if j > 0 else CENTER
        ws.row_dimensions[row].height = 80

    return ws


def normalize_step(step_def: dict, step_no: int) -> dict:
    """YAML上の短縮記法を正規化する.

    短縮記法:
        - { action: click, selector: "#btn" }
        - { verify: text, target: "#msg", expected: "OK" }
        - { verify: db, sql: "SELECT ...", expected: "rowcount:3" }
        - { action: include, sheet: "共通ログイン" }
    """
    tc = {"no": step_no}

    # item（テスト項目名）
    tc["item"] = step_def.get("item", "")

    # action 系
    action = step_def.get("action", "")
    tc["action"] = action
    tc["selector"] = step_def.get("selector", "")
    tc["input"] = step_def.get("input", "")

    # include の短縮記法: { action: include, sheet: "xxx" }
    if action == "include" and "sheet" in step_def:
        tc["input"] = step_def["sheet"]

    # verify 系: { verify: text, target: "#msg" } の短縮記法対応
    if "verify" in step_def:
        tc["verify_type"] = step_def["verify"]
        tc["verify_target"] = step_def.get(
            "target", step_def.get("sql",
                                   step_def.get("verify_target", "")))
    else:
        tc["verify_type"] = step_def.get("verify_type", "")
        tc["verify_target"] = step_def.get("verify_target", "")

    # db検証の短縮: { verify: db, sql: "SELECT ..." }
    if "sql" in step_def and not tc["verify_target"]:
        tc["verify_type"] = "db"
        tc["verify_target"] = step_def["sql"]

    tc["expected"] = step_def.get("expected", "")
    tc["note"] = step_def.get("note", "")

    # item が空の場合、action/verify から自動生成
    if not tc["item"]:
        if action == "include":
            tc["item"] = f"共通手順: {tc['input']}"
        elif action == "navigate":
            tc["item"] = f"ページを開く"
        elif action:
            tc["item"] = f"{action}: {tc['selector'] or tc['input']}"
        elif tc["verify_type"]:
            tc["item"] = f"検証: {tc['verify_type']}"

    return tc


def validate_steps(sheet_name: str, steps: list[dict]) -> list[str]:
    """テストステップのバリデーション."""
    errors = []
    for i, step in enumerate(steps):
        prefix = f"[{sheet_name}] Step {i + 1}"
        action = step.get("action", "")
        if action and action not in VALID_ACTIONS:
            errors.append(f"{prefix}: 無効な操作種別 '{action}'")

        verify = step.get("verify", step.get("verify_type", ""))
        if verify and verify not in VALID_VERIFY_TYPES:
            errors.append(f"{prefix}: 無効な検証種別 '{verify}'")

        if action in ("click", "input", "select", "hover", "wait_for",
                       "upload", "iframe") and not step.get("selector"):
            errors.append(f"{prefix}: action='{action}' にセレクタが未指定")

        if action == "navigate" and not step.get("input"):
            errors.append(f"{prefix}: action='navigate' にURLが未指定")

        if action == "include" and not step.get("input") and not step.get("sheet"):
            errors.append(f"{prefix}: action='include' にシート名が未指定")

    return errors


def gen_spec(yaml_path: str, output_path: str | None = None):
    """YAML定義からExcelテスト仕様書を生成する."""
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        print(f"エラー: ファイルが見つかりません: {yaml_path}", file=sys.stderr)
        sys.exit(1)

    with open(yaml_path, encoding="utf-8") as f:
        spec = yaml.safe_load(f) or {}

    sheets = spec.get("sheets", [])
    if not sheets:
        print("エラー: 'sheets' が定義されていません", file=sys.stderr)
        sys.exit(1)

    project_name = spec.get("project", "")

    # バリデーション
    all_errors = []
    for sheet_def in sheets:
        name = sheet_def.get("name", "Sheet")
        steps = sheet_def.get("steps", [])
        all_errors.extend(validate_steps(name, steps))

    if all_errors:
        print("バリデーションエラー:", file=sys.stderr)
        for err in all_errors:
            print(f"  {err}", file=sys.stderr)
        sys.exit(1)

    # Excel生成
    wb = Workbook()
    for i, sheet_def in enumerate(sheets):
        name = sheet_def.get("name", f"Sheet{i + 1}")
        steps = sheet_def.get("steps", [])
        test_cases = [normalize_step(s, j + 1) for j, s in enumerate(steps)]
        create_sheet(wb, name, test_cases, project_name, is_first=(i == 0))

    if output_path is None:
        output_path = yaml_path.with_suffix(".xlsx")
    output_path = Path(output_path)
    wb.save(str(output_path))
    print(f"テスト仕様書を生成しました: {output_path}")

    total_steps = sum(len(s.get("steps", [])) for s in sheets)
    print(f"  シート数: {len(sheets)}, 合計ステップ数: {total_steps}")


def main():
    parser = argparse.ArgumentParser(
        description="YAML テスト定義 → Excel テスト仕様書 生成ツール"
    )
    parser.add_argument("yaml_file", help="YAMLテスト定義ファイルのパス")
    parser.add_argument("-o", "--output", help="出力先Excelファイルのパス")
    args = parser.parse_args()
    gen_spec(args.yaml_file, args.output)


if __name__ == "__main__":
    main()
