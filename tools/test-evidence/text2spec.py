"""プレーンテキスト テスト定義 → spec dict 変換モジュール.

1行1ステップの簡易記法でテストを定義できる。
YAML の構文（インデント・括弧・コロン）を一切排除し、
既存の自然言語エンジンでテスト操作を自動解釈する。

行の種類:
    # テキスト        → シート名（新しいシートを開始）
    // テキスト       → コメント（無視）
    @key: value       → ディレクティブ（設定）
    空行              → 無視
    それ以外          → テストステップ（NL解釈される）

ディレクティブ:
    @project: 名前                          → プロジェクト名
    @base_url: http://...                   → ベースURL
    @selectors: 名前=#sel, 名前2=#sel2      → セレクタ辞書
    @data_source: file.csv                  → 現在シートのデータ駆動ソース

使い方:
    # gen_spec.py 経由（推奨）
    python gen_spec.py test.txt -o spec.xlsx

    # 単体で YAML に変換
    python text2spec.py test.txt -o test.yaml
"""

import argparse
import sys
from pathlib import Path

import yaml


def _parse_selectors_directive(value: str) -> dict[str, str]:
    """'名前=#sel, 名前2=#sel2' を辞書に変換する."""
    aliases = {}
    for pair in value.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            print(f"  警告: セレクタ定義の形式が不正です（=が必要）: {pair!r}",
                  file=sys.stderr)
            continue
        name, sel = pair.split("=", 1)
        aliases[name.strip()] = sel.strip()
    return aliases


def parse_text_spec(path: str | Path) -> dict:
    """テキストファイルを読み込み、gen_spec 互換の spec dict を返す.

    Args:
        path: テキストファイルのパス

    Returns:
        gen_spec() が受け取る形式の辞書:
        {"project": "...", "selectors": {...}, "sheets": [...]}
    """
    path = Path(path)

    # BOM 付き UTF-8 にも対応
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    project = ""
    selectors: dict[str, str] = {}
    base_url = ""
    sheets: list[dict] = []
    current_sheet_name: str | None = None
    current_steps: list[dict] = []
    current_data_source: str | None = None

    for line_no, raw_line in enumerate(lines, 1):
        line = raw_line.strip()

        # 空行・コメント
        if not line or line.startswith("//"):
            continue

        # ディレクティブ
        if line.startswith("@"):
            if ":" not in line:
                print(f"  警告 (行{line_no}): ディレクティブに ':' がありません: {line!r}",
                      file=sys.stderr)
                continue
            key, value = line[1:].split(":", 1)
            key = key.strip().lower()
            value = value.strip()

            if key == "project":
                project = value
            elif key == "base_url":
                base_url = value
            elif key == "selectors":
                selectors.update(_parse_selectors_directive(value))
            elif key == "data_source":
                current_data_source = value
            else:
                print(f"  警告 (行{line_no}): 不明なディレクティブ '@{key}'",
                      file=sys.stderr)
            continue

        # シート見出し
        if line.startswith("# ") or line == "#":
            # 前のシートをフラッシュ
            if current_sheet_name is not None or current_steps:
                sheet = {"name": current_sheet_name or "テスト",
                         "steps": current_steps}
                if current_data_source:
                    sheet["data_source"] = current_data_source
                sheets.append(sheet)

            current_sheet_name = line[2:].strip() if len(line) > 2 else f"Sheet{len(sheets) + 1}"
            current_steps = []
            current_data_source = None
            continue

        # テストステップ（NL 解釈は gen_spec のパイプラインに任せる）
        current_steps.append({"item": line})

    # 最終シートのフラッシュ
    if current_steps:
        sheet = {"name": current_sheet_name or "テスト",
                 "steps": current_steps}
        if current_data_source:
            sheet["data_source"] = current_data_source
        sheets.append(sheet)

    if not sheets:
        print("エラー: テスト定義が空です", file=sys.stderr)
        sys.exit(1)

    spec: dict = {"sheets": sheets}
    if project:
        spec["project"] = project
    if selectors:
        spec["selectors"] = selectors
    if base_url:
        spec.setdefault("environment", {})["base_url"] = base_url

    return spec


def main():
    parser = argparse.ArgumentParser(
        description="プレーンテキスト テスト定義 → YAML/Excel 変換"
    )
    parser.add_argument("input_file", help="テキストファイルのパス (.txt)")
    parser.add_argument("-o", "--output",
                        help="出力先 (.yaml で YAML、.xlsx で Excel)")
    args = parser.parse_args()

    spec = parse_text_spec(args.input_file)

    output = args.output
    if output is None:
        output = Path(args.input_file).with_suffix(".yaml")

    output = Path(output)
    if output.suffix.lower() in (".yml", ".yaml"):
        # YAML 出力
        with open(output, "w", encoding="utf-8") as f:
            yaml.dump(spec, f, allow_unicode=True, default_flow_style=False,
                      sort_keys=False)
        print(f"YAML を生成しました: {output}")
    elif output.suffix.lower() == ".xlsx":
        # Excel 出力（gen_spec に委譲）
        from gen_spec import gen_spec as _gen_spec
        # 一時 YAML を経由
        tmp_yaml = output.with_suffix(".tmp.yaml")
        with open(tmp_yaml, "w", encoding="utf-8") as f:
            yaml.dump(spec, f, allow_unicode=True, default_flow_style=False,
                      sort_keys=False)
        _gen_spec(str(tmp_yaml), str(output))
        tmp_yaml.unlink(missing_ok=True)
    else:
        print(f"エラー: 出力形式は .yaml または .xlsx のみ対応: {output}",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
