"""Playwright 録画スクリプト → YAML テスト定義 変換ツール.

Playwright の codegen で生成された Python スクリプトをパースし、
gen_spec.py で使える YAML テスト定義に変換する。

使い方:
    # 1. ブラウザ操作を録画
    python -m playwright codegen http://localhost:5000 -o recorded.py

    # 2. YAML に変換
    python record2spec.py recorded.py -o test_spec.yaml

    # 3. YAML を手動編集して検証ステップを追加

    # 4. Excel に変換
    python gen_spec.py test_spec.yaml -o spec.xlsx
"""

import argparse
import re
import sys
from pathlib import Path

import yaml


def parse_playwright_script(script: str) -> list[dict]:
    """Playwright codegen 出力の Python スクリプトをパースしてステップリストに変換する."""
    steps = []

    for line in script.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("import"):
            continue

        step = None

        # page.goto("url")
        m = re.search(r'page\.goto\(["\'](.+?)["\']\)', line)
        if m:
            step = {"action": "navigate", "input": m.group(1),
                    "item": "ページを開く"}

        # page.click("selector") / page.locator("selector").click()
        if step is None:
            m = re.search(r'page\.click\(["\'](.+?)["\']\)', line)
            if not m:
                m = re.search(r'page\.locator\(["\'](.+?)["\']\)\.click\(\)', line)
            if m:
                sel = m.group(1)
                step = {"action": "click", "selector": sel,
                        "item": f"クリック: {sel}"}

        # page.fill("selector", "value") / page.locator("selector").fill("value")
        if step is None:
            m = re.search(
                r'page\.fill\(["\'](.+?)["\'],\s*["\'](.+?)["\']\)', line)
            if not m:
                m = re.search(
                    r'page\.locator\(["\'](.+?)["\']\)\.fill\(["\'](.+?)["\']\)', line)
            if m:
                sel, val = m.group(1), m.group(2)
                step = {"action": "input", "selector": sel, "input": val,
                        "item": f"入力: {sel}"}

        # page.select_option("selector", "value")
        if step is None:
            m = re.search(
                r'page\.select_option\(["\'](.+?)["\'],\s*["\'](.+?)["\']\)', line)
            if not m:
                m = re.search(
                    r'page\.locator\(["\'](.+?)["\']\)\.select_option\(["\'](.+?)["\']\)', line)
            if m:
                sel, val = m.group(1), m.group(2)
                step = {"action": "select", "selector": sel, "input": val,
                        "item": f"選択: {sel} → {val}"}

        # page.press("selector", "key") / page.keyboard.press("key")
        if step is None:
            m = re.search(
                r'page\.press\(["\'](.+?)["\'],\s*["\'](.+?)["\']\)', line)
            if m:
                step = {"action": "keyboard", "input": m.group(2),
                        "item": f"キー入力: {m.group(2)}"}
            else:
                m = re.search(r'page\.keyboard\.press\(["\'](.+?)["\']\)', line)
                if m:
                    step = {"action": "keyboard", "input": m.group(1),
                            "item": f"キー入力: {m.group(1)}"}

        # page.hover("selector")
        if step is None:
            m = re.search(r'page\.hover\(["\'](.+?)["\']\)', line)
            if m:
                step = {"action": "hover", "selector": m.group(1),
                        "item": f"ホバー: {m.group(1)}"}

        # page.set_input_files("selector", "path")
        if step is None:
            m = re.search(
                r'page\.set_input_files\(["\'](.+?)["\'],\s*["\'](.+?)["\']\)', line)
            if m:
                step = {"action": "upload", "selector": m.group(1),
                        "input": m.group(2),
                        "item": f"アップロード: {m.group(1)}"}

        # expect(page.locator("selector")).to_be_visible()
        if step is None:
            m = re.search(
                r'expect\(page\.locator\(["\'](.+?)["\']\)\)\.to_be_visible\(\)', line)
            if m:
                step = {"verify": "visible", "target": m.group(1),
                        "item": f"表示確認: {m.group(1)}"}

        # expect(page.locator("selector")).to_have_text("text")
        if step is None:
            m = re.search(
                r'expect\(page\.locator\(["\'](.+?)["\']\)\)\.to_have_text\(["\'](.+?)["\']\)',
                line)
            if m:
                step = {"verify": "text", "target": m.group(1),
                        "expected": m.group(2),
                        "item": f"テキスト確認: {m.group(1)}"}

        if step:
            steps.append(step)

    return steps


def convert_to_yaml_spec(steps: list[dict], project: str = "",
                         sheet_name: str = "テスト") -> dict:
    """ステップリストをYAMLテスト定義の構造に変換する."""
    spec = {}
    if project:
        spec["project"] = project

    # スクリーンショットを要所に自動挿入
    enriched_steps = []
    for i, step in enumerate(steps):
        enriched_steps.append(step)
        # navigate の後にスクリーンショットを挿入
        if step.get("action") == "navigate":
            enriched_steps.append({
                "verify": "screenshot",
                "item": "画面表示の確認",
                "note": "TODO: 表示内容を確認",
            })

    # 末尾にスクリーンショットを追加
    if enriched_steps and enriched_steps[-1].get("verify") != "screenshot":
        enriched_steps.append({
            "verify": "screenshot",
            "item": "最終状態の確認",
        })

    spec["sheets"] = [{"name": sheet_name, "steps": enriched_steps}]
    return spec


def record2spec(script_path: str, output_path: str | None = None,
                project: str = "", sheet_name: str = "テスト"):
    """Playwright録画スクリプトをYAMLテスト定義に変換する."""
    script_path = Path(script_path)
    if not script_path.exists():
        print(f"エラー: ファイルが見つかりません: {script_path}", file=sys.stderr)
        sys.exit(1)

    script = script_path.read_text(encoding="utf-8")
    steps = parse_playwright_script(script)

    if not steps:
        print("警告: 操作が検出されませんでした", file=sys.stderr)

    spec = convert_to_yaml_spec(steps, project, sheet_name)

    if output_path is None:
        output_path = script_path.with_suffix(".yaml")
    output_path = Path(output_path)

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(spec, f, allow_unicode=True, default_flow_style=False,
                  sort_keys=False, width=120)

    print(f"YAML テスト定義を生成しました: {output_path}")
    print(f"  検出された操作: {len(steps)} ステップ")
    print(f"  次のステップ: {output_path} を編集して検証ステップを追加し、")
    print(f"  python gen_spec.py {output_path} で Excel に変換してください。")


def main():
    parser = argparse.ArgumentParser(
        description="Playwright 録画スクリプト → YAML テスト定義 変換ツール"
    )
    parser.add_argument("script", help="Playwright codegen で生成された Python スクリプト")
    parser.add_argument("-o", "--output", help="出力先 YAML ファイルのパス")
    parser.add_argument("--project", default="", help="プロジェクト名")
    parser.add_argument("--sheet", default="テスト", help="シート名（デフォルト: テスト）")
    args = parser.parse_args()
    record2spec(args.script, args.output, args.project, args.sheet)


if __name__ == "__main__":
    main()
