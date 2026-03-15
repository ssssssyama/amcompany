"""テストエビデンス自動化ツール - コアエンジン.

Excel仕様書を読み取り、Playwrightでブラウザ操作を実行し、
スクリーンショットと検証結果をExcelにエビデンスとして貼付する。
"""

import asyncio
import io
import shutil
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Font, PatternFill
from PIL import Image as PILImage
from playwright.async_api import async_playwright

# 定数
HEADER_ROW = 6
DATA_START_ROW = 7
COL_NO = "A"
COL_ITEM = "B"
COL_ACTION = "C"
COL_SELECTOR = "D"
COL_INPUT = "E"
COL_VERIFY_TYPE = "F"
COL_VERIFY_TARGET = "G"
COL_EXPECTED = "H"
COL_RESULT = "I"
COL_EVIDENCE = "J"
COL_NOTE = "K"

OK_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
OK_FONT = Font(name="Yu Gothic", size=10, bold=True, color="006100")
NG_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
NG_FONT = Font(name="Yu Gothic", size=10, bold=True, color="9C0006")
SKIP_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
SKIP_FONT = Font(name="Yu Gothic", size=10, color="9C6500")

EVIDENCE_IMG_WIDTH = 400
EVIDENCE_IMG_HEIGHT = 250


class TestStep:
    """テスト仕様書の1行を表すデータクラス."""

    def __init__(self, row: int, no, item, action, selector, input_val,
                 verify_type, verify_target, expected, note):
        self.row = row
        self.no = no
        self.item = item or ""
        self.action = (action or "").strip().lower()
        self.selector = selector or ""
        self.input_val = str(input_val) if input_val is not None else ""
        self.verify_type = (verify_type or "").strip().lower()
        self.verify_target = verify_target or ""
        self.expected = str(expected) if expected is not None else ""
        self.note = note or ""


def read_test_steps(ws) -> list[TestStep]:
    """テスト仕様書シートからテストステップを読み取る."""
    steps = []
    for row in range(DATA_START_ROW, ws.max_row + 1):
        no = ws[f"{COL_NO}{row}"].value
        if no is None:
            continue
        step = TestStep(
            row=row,
            no=no,
            item=ws[f"{COL_ITEM}{row}"].value,
            action=ws[f"{COL_ACTION}{row}"].value,
            selector=ws[f"{COL_SELECTOR}{row}"].value,
            input_val=ws[f"{COL_INPUT}{row}"].value,
            verify_type=ws[f"{COL_VERIFY_TYPE}{row}"].value,
            verify_target=ws[f"{COL_VERIFY_TARGET}{row}"].value,
            expected=ws[f"{COL_EXPECTED}{row}"].value,
            note=ws[f"{COL_NOTE}{row}"].value,
        )
        steps.append(step)
    return steps


async def execute_action(page, step: TestStep):
    """ブラウザ操作を実行する."""
    if step.action == "navigate":
        await page.goto(step.input_val, wait_until="networkidle")
    elif step.action == "click":
        await page.click(step.selector)
        await page.wait_for_load_state("networkidle")
    elif step.action == "input":
        await page.fill(step.selector, step.input_val)
    elif step.action == "select":
        await page.select_option(step.selector, step.input_val)
    elif step.action == "wait":
        ms = int(step.input_val) if step.input_val else 1000
        await asyncio.sleep(ms / 1000)


async def take_screenshot(page, output_dir: Path, step_no) -> Path:
    """スクリーンショットを撮影して保存する."""
    screenshot_path = output_dir / f"step_{step_no}.png"
    await page.screenshot(path=str(screenshot_path), full_page=False)
    return screenshot_path


async def verify_screen(page, step: TestStep) -> tuple[bool, str]:
    """画面上の要素を検証する."""
    if step.verify_type == "text":
        element = await page.query_selector(step.verify_target)
        if element is None:
            return False, f"要素が見つかりません: {step.verify_target}"
        actual = await element.text_content()
        actual = (actual or "").strip()
        if actual == step.expected:
            return True, f"OK: '{actual}'"
        return False, f"NG: 期待値='{step.expected}', 実際='{actual}'"

    elif step.verify_type == "value":
        element = await page.query_selector(step.verify_target)
        if element is None:
            return False, f"要素が見つかりません: {step.verify_target}"
        actual = await element.get_attribute("value") or ""
        if actual == step.expected:
            return True, f"OK: '{actual}'"
        return False, f"NG: 期待値='{step.expected}', 実際='{actual}'"

    elif step.verify_type == "visible":
        element = await page.query_selector(step.verify_target)
        if element is None:
            return False, f"要素が見つかりません: {step.verify_target}"
        is_visible = await element.is_visible()
        if is_visible:
            return True, "OK: 要素は表示されています"
        return False, "NG: 要素が表示されていません"

    elif step.verify_type == "url":
        actual_url = page.url
        if actual_url == step.expected:
            return True, f"OK: URL一致"
        return False, f"NG: 期待値='{step.expected}', 実際='{actual_url}'"

    elif step.verify_type == "screenshot":
        return True, "スクリーンショット取得"

    return True, ""


def verify_db(step: TestStep, db_engine) -> tuple[bool, str]:
    """DBに接続してクエリ結果を検証する."""
    if db_engine is None:
        return False, "DB接続が設定されていません"

    from sqlalchemy import text

    with db_engine.connect() as conn:
        result = conn.execute(text(step.verify_target))
        row = result.fetchone()
        if row is None:
            actual = "NULL"
        else:
            actual = str(row[0])

    if actual == step.expected:
        return True, f"OK: DB結果='{actual}'"
    return False, f"NG: 期待値='{step.expected}', DB結果='{actual}'"


def resize_screenshot(screenshot_path: Path) -> bytes:
    """スクリーンショットをエビデンス用にリサイズする."""
    with PILImage.open(screenshot_path) as img:
        img.thumbnail((EVIDENCE_IMG_WIDTH, EVIDENCE_IMG_HEIGHT))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def write_result(ws, step: TestStep, passed: bool | None, message: str,
                 screenshot_path: Path | None):
    """検証結果とエビデンスをExcelに書き込む."""
    result_cell = ws[f"{COL_RESULT}{step.row}"]
    evidence_cell = ws[f"{COL_EVIDENCE}{step.row}"]

    if passed is True:
        result_cell.value = "OK"
        result_cell.fill = OK_FILL
        result_cell.font = OK_FONT
    elif passed is False:
        result_cell.value = "NG"
        result_cell.fill = NG_FILL
        result_cell.font = NG_FONT
    else:
        result_cell.value = "SKIP"
        result_cell.fill = SKIP_FILL
        result_cell.font = SKIP_FONT

    # メッセージをノート欄に追記
    if message:
        note_cell = ws[f"{COL_NOTE}{step.row}"]
        existing = note_cell.value or ""
        note_cell.value = f"{existing}\n{message}".strip() if existing else message

    # スクリーンショットをエビデンス列に貼付
    if screenshot_path and screenshot_path.exists():
        img_data = resize_screenshot(screenshot_path)
        img_stream = io.BytesIO(img_data)
        img = ExcelImage(img_stream)
        img.width = EVIDENCE_IMG_WIDTH
        img.height = EVIDENCE_IMG_HEIGHT
        ws.add_image(img, f"{COL_EVIDENCE}{step.row}")
        ws.row_dimensions[step.row].height = EVIDENCE_IMG_HEIGHT * 0.75


async def run_tests(spec_path: str, output_path: str | None = None,
                    db_url: str | None = None, headless: bool = True):
    """テスト仕様書を実行してエビデンスを生成する.

    Args:
        spec_path: テスト仕様書Excelのパス
        output_path: エビデンス出力先Excelのパス（省略時は元ファイルに _evidence を付与）
        db_url: DB接続URL（例: postgresql://user:pass@localhost/dbname）
        headless: ヘッドレスモードで実行するか
    """
    spec_path = Path(spec_path)
    if output_path is None:
        output_path = spec_path.parent / f"{spec_path.stem}_evidence{spec_path.suffix}"
    output_path = Path(output_path)

    # 元ファイルをコピーして出力用にする
    shutil.copy2(spec_path, output_path)
    wb = load_workbook(str(output_path))
    ws = wb["テスト仕様書"]

    # テスト日を記入
    ws["B3"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # テストステップを読み取り
    steps = read_test_steps(ws)
    if not steps:
        print("テストステップが見つかりません。")
        return

    print(f"テスト仕様書を読み込みました: {len(steps)} ステップ")

    # スクリーンショット保存ディレクトリ
    screenshot_dir = output_path.parent / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)

    # DB接続（オプション）
    db_engine = None
    if db_url:
        from sqlalchemy import create_engine
        db_engine = create_engine(db_url)
        print(f"DB接続: {db_url}")

    # ブラウザ起動
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="ja-JP",
        )
        page = await context.new_page()

        for step in steps:
            print(f"  Step {step.no}: {step.item}...", end=" ")

            screenshot_path = None
            passed = None
            message = ""

            try:
                # ブラウザ操作を実行
                if step.action:
                    await execute_action(page, step)

                # スクリーンショット撮影（操作がある場合、またはscreenshot検証の場合）
                if step.action or step.verify_type == "screenshot":
                    screenshot_path = await take_screenshot(
                        page, screenshot_dir, step.no
                    )

                # 検証
                if step.verify_type == "db":
                    passed, message = verify_db(step, db_engine)
                elif step.verify_type:
                    passed, message = await verify_screen(page, step)
                else:
                    passed = True
                    message = "操作完了"

            except Exception as e:
                passed = False
                message = f"エラー: {e}"
                # エラー時もスクリーンショットを試みる
                try:
                    screenshot_path = await take_screenshot(
                        page, screenshot_dir, f"{step.no}_error"
                    )
                except Exception:
                    pass

            # 結果をExcelに書き込み
            write_result(ws, step, passed, message, screenshot_path)

            status = "OK" if passed else ("NG" if passed is False else "SKIP")
            print(f"[{status}] {message}")

        await browser.close()

    # ワークブックを保存
    wb.save(str(output_path))
    print(f"\nエビデンスを保存しました: {output_path}")

    # サマリー表示
    ok_count = sum(1 for s in steps if ws[f"{COL_RESULT}{s.row}"].value == "OK")
    ng_count = sum(1 for s in steps if ws[f"{COL_RESULT}{s.row}"].value == "NG")
    total = len(steps)
    print(f"結果: {ok_count}/{total} OK, {ng_count}/{total} NG")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="テストエビデンス自動化ツール - Excel仕様書からテスト実行+エビデンス生成"
    )
    parser.add_argument("spec", help="テスト仕様書Excelファイルのパス")
    parser.add_argument("-o", "--output", help="エビデンス出力先のパス")
    parser.add_argument("--db-url", help="DB接続URL (例: postgresql://user:pass@host/db)")
    parser.add_argument("--headed", action="store_true", help="ブラウザを表示して実行")

    args = parser.parse_args()
    asyncio.run(run_tests(
        spec_path=args.spec,
        output_path=args.output,
        db_url=args.db_url,
        headless=not args.headed,
    ))


if __name__ == "__main__":
    main()
