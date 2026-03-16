"""テストエビデンス自動化ツール - コアエンジン.

Excel仕様書を読み取り、Playwrightでブラウザ操作を実行し、
スクリーンショットと検証結果をExcelにエビデンスとして貼付する。
"""

import asyncio
import csv
import io
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Font, PatternFill
from PIL import Image as PILImage
from playwright.async_api import async_playwright

from project_config import ProjectConfig

# ログ設定
logger = logging.getLogger("test-evidence")

# スタイル定数
OK_FILL = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
OK_FONT = Font(name="Yu Gothic", size=10, bold=True, color="006100")
NG_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
NG_FONT = Font(name="Yu Gothic", size=10, bold=True, color="9C0006")
SKIP_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
SKIP_FONT = Font(name="Yu Gothic", size=10, color="9C6500")

EVIDENCE_IMG_WIDTH_DEFAULT = 400
EVIDENCE_IMG_HEIGHT_DEFAULT = 250


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


class StopTestError(Exception):
    """NG時にテスト実行を中断するための例外."""


def read_test_steps(ws, config: ProjectConfig) -> list[TestStep]:
    """テスト仕様書シートからテストステップを読み取る.

    config の excel セクションで列マッピング・ヘッダー行を制御可能。
    セレクタ・入力値・期待値等の ${変数名} を設定ファイルの値で置換する。
    """
    resolve = config.resolve
    col_map = config.excel_columns
    data_start = config.excel_data_start_row

    steps = []
    for row in range(data_start, ws.max_row + 1):
        no = ws[f"{col_map['no']}{row}"].value
        if no is None:
            continue
        step = TestStep(
            row=row,
            no=no,
            item=ws[f"{col_map['item']}{row}"].value,
            action=ws[f"{col_map['action']}{row}"].value,
            selector=resolve(ws[f"{col_map['selector']}{row}"].value or ""),
            input_val=resolve(
                str(ws[f"{col_map['input']}{row}"].value)
                if ws[f"{col_map['input']}{row}"].value is not None else ""
            ),
            verify_type=ws[f"{col_map['verify_type']}{row}"].value,
            verify_target=resolve(ws[f"{col_map['verify_target']}{row}"].value or ""),
            expected=resolve(
                str(ws[f"{col_map['expected']}{row}"].value)
                if ws[f"{col_map['expected']}{row}"].value is not None else ""
            ),
            note=ws[f"{col_map['note']}{row}"].value,
        )
        steps.append(step)
    return steps


async def execute_action(page, step: TestStep):
    """ブラウザ操作を実行する."""
    action = step.action

    if action == "navigate":
        await page.goto(step.input_val, wait_until="networkidle")

    elif action == "click":
        await page.click(step.selector)
        await page.wait_for_load_state("networkidle")

    elif action == "input":
        await page.fill(step.selector, step.input_val)

    elif action == "select":
        await page.select_option(step.selector, step.input_val)

    elif action == "wait":
        ms = int(step.input_val) if step.input_val else 1000
        await asyncio.sleep(ms / 1000)

    elif action == "wait_for":
        # input欄に "hidden:10000" と書くと state="hidden" で待機
        wait_state = "visible"
        wait_timeout = 30000
        if step.input_val:
            if step.input_val.startswith("hidden"):
                wait_state = "hidden"
                parts = step.input_val.split(":", 1)
                if len(parts) == 2 and parts[1].strip().isdigit():
                    wait_timeout = int(parts[1].strip())
            elif step.input_val.isdigit():
                wait_timeout = int(step.input_val)
        await page.wait_for_selector(step.selector, state=wait_state, timeout=wait_timeout)

    elif action == "upload":
        await page.set_input_files(step.selector, step.input_val)

    elif action == "hover":
        await page.hover(step.selector)

    elif action == "scroll":
        if step.selector:
            await page.eval_on_selector(
                step.selector,
                "el => el.scrollIntoView({behavior: 'smooth', block: 'center'})",
            )
        else:
            y = int(step.input_val) if step.input_val else 500
            await page.evaluate(f"window.scrollBy(0, {y})")

    elif action == "keyboard":
        await page.keyboard.press(step.input_val)

    elif action == "alert_accept":
        page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))

    elif action == "alert_dismiss":
        page.once("dialog", lambda d: asyncio.ensure_future(d.dismiss()))

    elif action == "iframe":
        # iframe内の操作は次ステップ以降で使えるようframeを返す
        # （現状は指定セレクタのiframeにフォーカス切り替え）
        frame = page.frame_locator(step.selector)
        return frame

    else:
        logger.warning(f"未知の操作種別: {action}")


async def take_screenshot(page, output_dir: Path, step_no,
                          element_selector: str | None = None) -> Path:
    """スクリーンショットを撮影して保存する.

    element_selector が指定された場合、その要素のみをキャプチャする。
    """
    screenshot_path = output_dir / f"step_{step_no}.png"
    if element_selector:
        element = await page.query_selector(element_selector)
        if element:
            await element.screenshot(path=str(screenshot_path))
            return screenshot_path
    await page.screenshot(path=str(screenshot_path), full_page=False)
    return screenshot_path


def _match_expected(actual: str, expected: str) -> tuple[bool, str]:
    """期待値と実際値を照合する.

    期待値のプレフィックスで照合方式を制御:
    - "contains:" → 部分一致
    - "regex:"    → 正規表現マッチ
    - (プレフィックスなし) → 完全一致

    ※ DB検証専用プレフィックス (rowcount: / empty / rows:) は
      verify_db_sqlite / verify_db_a5m2 内で処理済みのため、ここには来ない。
    """
    if expected.startswith("contains:"):
        pattern = expected[len("contains:"):]
        if pattern in actual:
            return True, f"OK: '{actual}' に '{pattern}' を含む"
        return False, f"NG: '{actual}' に '{pattern}' が含まれない"

    if expected.startswith("regex:"):
        pattern = expected[len("regex:"):]
        if re.search(pattern, actual):
            return True, f"OK: '{actual}' が /{pattern}/ にマッチ"
        return False, f"NG: '{actual}' が /{pattern}/ にマッチしない"

    # 完全一致
    if actual == expected:
        return True, f"OK: '{actual}'"
    return False, f"NG: 期待値='{expected}', 実際='{actual}'"


async def verify_screen(page, step: TestStep) -> tuple[bool, str]:
    """画面上の要素を検証する."""
    if step.verify_type == "text":
        element = await page.query_selector(step.verify_target)
        if element is None:
            return False, f"要素が見つかりません: {step.verify_target}"
        actual = (await element.text_content() or "").strip()
        return _match_expected(actual, step.expected)

    elif step.verify_type == "value":
        element = await page.query_selector(step.verify_target)
        if element is None:
            return False, f"要素が見つかりません: {step.verify_target}"
        actual = await element.get_attribute("value") or ""
        return _match_expected(actual, step.expected)

    elif step.verify_type == "visible":
        element = await page.query_selector(step.verify_target)
        if element is None:
            return False, f"要素が見つかりません: {step.verify_target}"
        is_visible = await element.is_visible()
        if is_visible:
            return True, "OK: 要素は表示されています"
        return False, "NG: 要素が表示されていません"

    elif step.verify_type == "hidden":
        element = await page.query_selector(step.verify_target)
        if element is None:
            return True, "OK: 要素が存在しません（非表示）"
        is_visible = await element.is_visible()
        if not is_visible:
            return True, "OK: 要素は非表示です"
        return False, "NG: 要素が表示されています"

    elif step.verify_type == "url":
        actual_url = page.url
        return _match_expected(actual_url, step.expected)

    elif step.verify_type == "screenshot":
        return True, "スクリーンショット取得"

    return True, ""


def _match_db_result(rows: list, columns: list[str], expected: str) -> tuple[bool, str]:
    """DB検証の期待値照合.

    拡張プレフィックス:
    - "empty"          → 結果が0行であることを検証
    - "not_empty"      → 結果が1行以上あることを検証
    - "rowcount:N"     → 結果がN行であることを検証
    - "rowcount:>=N"   → 結果がN行以上であることを検証
    - "rows:col=v,..."  → 1行目の指定カラム値を検証（カンマ区切り）
    - "rows_any:col=v,..." → いずれかの行が条件を満たすことを検証
    - "rows_all:col=v,..." → 全行が条件を満たすことを検証
    - "values:v1,v2,..."   → 1列目の全値リストを順序付きで検証
    - 上記以外          → 1行目1列目の値を _match_expected で照合
    """
    if expected == "empty":
        if len(rows) == 0:
            return True, "OK: 結果は0行（空）"
        return False, f"NG: 結果が空ではありません（{len(rows)}行）"

    if expected == "not_empty":
        if len(rows) > 0:
            return True, f"OK: 結果は{len(rows)}行（空ではない）"
        return False, "NG: 結果が空です"

    if expected.startswith("rowcount:"):
        expr = expected[len("rowcount:"):]
        actual_count = len(rows)

        # 比較演算子付き: rowcount:>=3, rowcount:<=5, rowcount:>0
        m = re.match(r"^(>=|<=|>|<)(\d+)$", expr)
        if m:
            op, val = m.group(1), int(m.group(2))
            ops = {">=": actual_count >= val, "<=": actual_count <= val,
                   ">": actual_count > val, "<": actual_count < val}
            if ops[op]:
                return True, f"OK: 行数={actual_count} ({op}{val})"
            return False, f"NG: 行数={actual_count} (期待: {op}{val})"

        # 数値のみ: rowcount:3
        expected_count = int(expr)
        if actual_count == expected_count:
            return True, f"OK: 行数={actual_count}"
        return False, f"NG: 行数 期待={expected_count}, 実際={actual_count}"

    if expected.startswith("rows:"):
        # rows:status=完了,priority=高  → 1行目の指定カラムを検証
        checks = expected[len("rows:"):]
        if not rows:
            return False, "NG: 結果が空です"
        col_map = {c: i for i, c in enumerate(columns)}
        errors = []
        for pair in checks.split(","):
            col_name, exp_val = pair.split("=", 1)
            col_name = col_name.strip()
            exp_val = exp_val.strip()
            if col_name not in col_map:
                errors.append(f"カラム'{col_name}'が存在しない")
                continue
            actual_val = str(rows[0][col_map[col_name]])
            if actual_val != exp_val:
                errors.append(f"{col_name}: 期待='{exp_val}', 実際='{actual_val}'")
        if errors:
            return False, "NG: " + "; ".join(errors)
        return True, f"OK: {checks}"

    if expected.startswith("rows_any:"):
        # rows_any:col=v,...  → いずれかの行が全条件を満たせばOK
        checks = expected[len("rows_any:"):]
        if not rows:
            return False, "NG: 結果が空です"
        col_map = {c: i for i, c in enumerate(columns)}
        pairs = []
        for pair in checks.split(","):
            col_name, exp_val = pair.split("=", 1)
            col_name = col_name.strip()
            exp_val = exp_val.strip()
            if col_name not in col_map:
                return False, f"NG: カラム'{col_name}'が存在しない"
            pairs.append((col_name, col_map[col_name], exp_val))
        for row in rows:
            if all(str(row[idx]) == exp_val for _, idx, exp_val in pairs):
                return True, f"OK: 条件に一致する行あり ({checks})"
        return False, f"NG: 条件を満たす行がありません ({checks}, {len(rows)}行中)"

    if expected.startswith("rows_all:"):
        # rows_all:col=v,...  → 全行が条件を満たすことを検証
        checks = expected[len("rows_all:"):]
        if not rows:
            return False, "NG: 結果が空です"
        col_map = {c: i for i, c in enumerate(columns)}
        pairs = []
        for pair in checks.split(","):
            col_name, exp_val = pair.split("=", 1)
            col_name = col_name.strip()
            exp_val = exp_val.strip()
            if col_name not in col_map:
                return False, f"NG: カラム'{col_name}'が存在しない"
            pairs.append((col_name, col_map[col_name], exp_val))
        for i, row in enumerate(rows):
            for col_name, idx, exp_val in pairs:
                actual_val = str(row[idx])
                if actual_val != exp_val:
                    return False, f"NG: 行{i + 1} {col_name}: 期待='{exp_val}', 実際='{actual_val}'"
        return True, f"OK: 全{len(rows)}行が条件を満たす ({checks})"

    if expected.startswith("values:"):
        # values:v1,v2,...  → 1列目の全値リストを順序付きで検証
        expected_values = [v.strip() for v in expected[len("values:"):].split(",")]
        actual_values = [str(row[0]) for row in rows]
        if actual_values == expected_values:
            return True, f"OK: values={','.join(actual_values)}"
        return False, f"NG: 期待={expected_values}, 実際={actual_values}"

    # デフォルト: 1行目1列目を比較
    if not rows:
        actual = "NULL"
    else:
        actual = str(rows[0][0])
    return _match_expected(actual, expected)


def verify_db_sqlite(step: TestStep, db_path: str) -> tuple[bool, str]:
    """SQLiteデータベースに直接接続してSQLを実行し、結果を検証する."""
    import sqlite3 as _sqlite3

    if not db_path or not Path(db_path).exists():
        return False, f"SQLiteデータベースが見つかりません: {db_path}"

    try:
        conn = _sqlite3.connect(db_path)
        cursor = conn.execute(step.verify_target)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        return False, f"SQLiteエラー: {e}"

    return _match_db_result(rows, columns, step.expected)


def verify_db_a5m2(step: TestStep, a5m2_cmd: str, a5m2_connect: str) -> tuple[bool, str]:
    """A5M2cmd経由でSQLを実行し、CSV出力された結果を検証する."""
    if not a5m2_cmd:
        return False, "A5M2cmdのパスが設定されていません"

    with tempfile.TemporaryDirectory() as tmpdir:
        sql_path = Path(tmpdir) / "query.sql"
        sql_path.write_text(step.verify_target, encoding="utf-8")

        cmd = [
            a5m2_cmd,
            f"/Connect={a5m2_connect}",
            "/RunSQL",
            f"/FileName={sql_path}",
            f"/OutputPath={tmpdir}",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
                encoding="utf-8",
            )
        except FileNotFoundError:
            return False, f"A5M2cmdが見つかりません: {a5m2_cmd}"
        except subprocess.TimeoutExpired:
            return False, "A5M2cmd: タイムアウト（30秒）"

        if result.returncode != 0:
            return False, f"A5M2cmdエラー: {result.stderr.strip()}"

        csv_path = Path(tmpdir) / "Query-1.csv"
        if not csv_path.exists():
            return False, "A5M2cmd: クエリ結果のCSVが出力されませんでした"

        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None) or []
            rows = [row for row in reader]

    return _match_db_result(rows, header, step.expected)


def resize_screenshot(screenshot_path: Path,
                      width: int = EVIDENCE_IMG_WIDTH_DEFAULT,
                      height: int = EVIDENCE_IMG_HEIGHT_DEFAULT) -> bytes:
    """スクリーンショットをエビデンス用にリサイズする."""
    with PILImage.open(screenshot_path) as img:
        img.thumbnail((width, height))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def write_result(ws, col_map: dict, step: TestStep, passed: bool | None,
                 message: str, screenshot_path: Path | None,
                 img_width: int = EVIDENCE_IMG_WIDTH_DEFAULT,
                 img_height: int = EVIDENCE_IMG_HEIGHT_DEFAULT):
    """検証結果とエビデンスをExcelに書き込む."""
    result_cell = ws[f"{col_map['result']}{step.row}"]
    evidence_col = col_map["evidence"]

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
        note_cell = ws[f"{col_map['note']}{step.row}"]
        existing = note_cell.value or ""
        note_cell.value = f"{existing}\n{message}".strip() if existing else message

    # スクリーンショットをエビデンス列に貼付
    if screenshot_path and screenshot_path.exists():
        img_data = resize_screenshot(screenshot_path, img_width, img_height)
        img_stream = io.BytesIO(img_data)
        img = ExcelImage(img_stream)
        img.width = img_width
        img.height = img_height
        ws.add_image(img, f"{evidence_col}{step.row}")
        ws.row_dimensions[step.row].height = img_height * 0.75


async def authenticate(page, config: ProjectConfig):
    """設定ファイルの認証情報に基づいてログイン処理を行う."""
    auth = config.auth
    auth_type = config.auth_type

    if auth_type == "form":
        login_url = config.resolve(auth.get("login_url", ""))
        if login_url:
            await page.goto(login_url, wait_until="networkidle")
        for field in auth.get("fields", []):
            selector = field.get("selector", "")
            value = config.resolve(field.get("value", ""))
            await page.fill(selector, value)
        submit = auth.get("submit_selector", "")
        if submit:
            await page.click(submit)
            await page.wait_for_load_state("networkidle")
        logger.info("認証完了 (form)")

    elif auth_type == "basic":
        logger.info("認証設定済み (basic)")

    elif auth_type == "cookie":
        for cookie in auth.get("cookies", []):
            await page.context.add_cookies([cookie])
        logger.info(f"認証完了 (cookie: {len(auth.get('cookies', []))}件)")


async def run_sheet(page, ws, config: ProjectConfig, screenshot_dir: Path,
                    effective_a5m2_cmd: str, effective_a5m2_connect: str,
                    sheet_name: str,
                    step_filter: set[int] | None = None) -> tuple[int, int, int, list]:
    """1シート分のテストを実行する.

    Args:
        step_filter: 実行対象のステップNo.集合（Noneなら全ステップ実行）

    Returns:
        (ok_count, ng_count, skip_count, ng_details)
    """
    col_map = config.excel_columns
    on_fail = config.on_fail
    img_w = config.screenshot_width
    img_h = config.screenshot_height

    steps = read_test_steps(ws, config)
    if not steps:
        logger.info(f"[{sheet_name}] テストステップが見つかりません。")
        return 0, 0, 0, []

    total_steps = len(steps)
    logger.info(f"[{sheet_name}] {total_steps} ステップを実行")

    aborted = False
    ng_details = []  # NG一覧を収集
    for idx, step in enumerate(steps, 1):
        step_start = time.monotonic()
        logger.info(f"  [{idx}/{total_steps}] Step {step.no}: {step.item}...")

        screenshot_path = None
        passed = None
        message = ""

        # action=skip: 事前スキップ指定
        if step.action == "skip":
            passed = None
            message = "スキップ指定 (action=skip)"
            write_result(ws, col_map, step, passed, message, None, img_w, img_h)
            elapsed = time.monotonic() - step_start
            logger.info(f"  [{idx}/{total_steps}] Step {step.no}: [SKIP] {message} ({elapsed:.1f}s)")
            continue

        # --steps フィルタによるスキップ
        if step_filter is not None:
            step_no_int = int(step.no) if str(step.no).isdigit() else None
            if step_no_int is None or step_no_int not in step_filter:
                passed = None
                message = "範囲外 (--steps フィルタ)"
                write_result(ws, col_map, step, passed, message, None, img_w, img_h)
                elapsed = time.monotonic() - step_start
                logger.info(f"  [{idx}/{total_steps}] Step {step.no}: [SKIP] {message} ({elapsed:.1f}s)")
                continue

        if aborted:
            passed = None
            message = "前ステップのNG/エラーにより中断"
            write_result(ws, col_map, step, passed, message, None, img_w, img_h)
            elapsed = time.monotonic() - step_start
            logger.info(f"  [{idx}/{total_steps}] Step {step.no}: [SKIP] {message} ({elapsed:.1f}s)")
            continue

        try:
            # ブラウザ操作を実行
            if step.action:
                await execute_action(page, step)

            # スクリーンショット撮影
            if step.action or step.verify_type == "screenshot":
                screenshot_path = await take_screenshot(
                    page, screenshot_dir, f"{sheet_name}_{step.no}",
                )

            # 検証
            if step.verify_type == "db":
                if config.db_type == "sqlite" and config.sqlite_path:
                    passed, message = verify_db_sqlite(
                        step, config.sqlite_path,
                    )
                else:
                    passed, message = verify_db_a5m2(
                        step,
                        effective_a5m2_cmd or "",
                        effective_a5m2_connect or "",
                    )
            elif step.verify_type:
                passed, message = await verify_screen(page, step)
            else:
                passed = True
                message = "操作完了"

        except Exception as e:
            passed = False
            message = f"エラー: {e}"
            logger.debug(f"  Step {step.no} 例外詳細:\n{traceback.format_exc()}")
            try:
                screenshot_path = await take_screenshot(
                    page, screenshot_dir, f"{sheet_name}_{step.no}_error",
                )
            except Exception:
                pass

        # 結果をExcelに書き込み
        write_result(ws, col_map, step, passed, message, screenshot_path, img_w, img_h)

        elapsed = time.monotonic() - step_start
        status = "OK" if passed else ("NG" if passed is False else "SKIP")
        logger.info(f"  [{idx}/{total_steps}] Step {step.no}: [{status}] {message} ({elapsed:.1f}s)")

        # NG情報を収集
        if passed is False:
            ng_details.append({
                "sheet": sheet_name,
                "step_no": step.no,
                "item": step.item,
                "message": message,
            })

        # NG時の制御
        if passed is False and on_fail == "abort":
            logger.warning(f"  NG検出 → テスト中断 (on_fail=abort)")
            aborted = True

    # サマリー集計
    ok = sum(1 for s in steps if ws[f"{col_map['result']}{s.row}"].value == "OK")
    ng = sum(1 for s in steps if ws[f"{col_map['result']}{s.row}"].value == "NG")
    skip = sum(1 for s in steps if ws[f"{col_map['result']}{s.row}"].value == "SKIP")
    return ok, ng, skip, ng_details


def _parse_step_range(step_range: str) -> set[int]:
    """'1-5,10,15-20' 形式のステップ範囲をパースして整数集合を返す."""
    result = set()
    for part in step_range.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            result.update(range(int(start), int(end) + 1))
        else:
            result.add(int(part))
    return result


def _validate_spec(wb, config: ProjectConfig, target_sheets: list[str]) -> list[str]:
    """テスト仕様書の形式チェック（ドライラン）.

    Returns:
        エラーメッセージのリスト（空なら問題なし）
    """
    valid_actions = {
        "navigate", "click", "input", "select", "wait", "wait_for",
        "upload", "hover", "scroll", "keyboard",
        "alert_accept", "alert_dismiss", "iframe", "skip", "",
    }
    valid_verify_types = {
        "text", "value", "visible", "hidden", "url", "screenshot", "db", "",
    }
    errors = []

    for sheet_name in target_sheets:
        if sheet_name not in wb.sheetnames:
            errors.append(f"[{sheet_name}] シートが存在しません")
            continue
        ws = wb[sheet_name]
        steps = read_test_steps(ws, config)
        for step in steps:
            prefix = f"[{sheet_name}] Step {step.no}"
            if step.action and step.action not in valid_actions:
                errors.append(f"{prefix}: 無効な操作種別 '{step.action}'")
            if step.verify_type and step.verify_type not in valid_verify_types:
                errors.append(f"{prefix}: 無効な検証種別 '{step.verify_type}'")
            if step.action in ("click", "input", "select", "hover", "wait_for",
                               "upload", "iframe") and not step.selector:
                errors.append(f"{prefix}: action='{step.action}' にセレクタが未指定")
            if step.action == "navigate" and not step.input_val:
                errors.append(f"{prefix}: action='navigate' にURLが未指定")
            if step.verify_type in ("text", "value", "visible", "hidden") and not step.verify_target:
                errors.append(f"{prefix}: verify_type='{step.verify_type}' に検証対象が未指定")
            if step.verify_type == "db" and not step.verify_target:
                errors.append(f"{prefix}: verify_type='db' にSQLが未指定")
    return errors


async def run_tests(spec_path: str, output_path: str | None = None,
                    config_path: str | None = None,
                    a5m2_cmd: str | None = None,
                    a5m2_connect: str | None = None,
                    headless: bool = True,
                    sheets: list[str] | None = None,
                    step_range: str | None = None,
                    dry_run: bool = False,
                    json_report: str | None = None):
    """テスト仕様書を実行してエビデンスを生成する.

    Args:
        spec_path: テスト仕様書Excelのパス
        output_path: エビデンス出力先Excelのパス（省略時は元ファイルに _evidence を付与）
        config_path: プロジェクト設定ファイル（YAML）のパス
        a5m2_cmd: A5M2cmd.exe のパス（設定ファイルより優先）
        a5m2_connect: A5M2の接続文字列（設定ファイルより優先）
        headless: ヘッドレスモードで実行するか
        sheets: 実行対象のシート名リスト（省略時は設定ファイルの指定またはデフォルト）
        step_range: 実行対象のステップ範囲（例: '10-15,20'）
        dry_run: Trueなら形式チェックのみ（ブラウザ起動なし）
        json_report: JSON結果レポートの出力先パス
    """
    # プロジェクト設定を読み込み
    config = ProjectConfig(config_path)

    spec_path = Path(spec_path)
    if output_path is None:
        output_path = spec_path.parent / f"{spec_path.stem}_evidence{spec_path.suffix}"
    output_path = Path(output_path)

    # ログファイル設定
    log_path = output_path.parent / f"{output_path.stem}.log"
    _setup_logging(log_path)

    logger.info(f"テスト仕様書: {spec_path}")
    if config_path:
        logger.info(f"プロジェクト設定: {config_path}")

    # 元ファイルをコピーして出力用にする
    shutil.copy2(spec_path, output_path)
    wb = load_workbook(str(output_path))

    # 実行対象シートを決定
    target_sheets = sheets or config.excel_sheets
    if not target_sheets:
        # 凡例シートを除外して全シートを対象にする
        target_sheets = [name for name in wb.sheetnames if name != "凡例"]

    logger.info(f"対象シート: {target_sheets}")

    # ドライラン: 形式チェックのみ
    if dry_run:
        logger.info("ドライラン: 仕様書の形式チェックを実行")
        errors = _validate_spec(wb, config, target_sheets)
        if errors:
            for err in errors:
                logger.error(f"  {err}")
            logger.info(f"ドライラン結果: {len(errors)} 件のエラー")
        else:
            logger.info("ドライラン結果: エラーなし")
        return (0, 0, 0) if errors else (1, 0, 0)

    # ステップ範囲フィルタ
    step_filter = _parse_step_range(step_range) if step_range else None
    if step_filter:
        logger.info(f"ステップフィルタ: {sorted(step_filter)}")

    # スクリーンショット保存ディレクトリ
    screenshot_dir = output_path.parent / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)

    # A5M2設定: CLI引数 > 設定ファイル
    effective_a5m2_cmd = a5m2_cmd or config.a5m2_cmd or ""
    effective_a5m2_connect = a5m2_connect or config.a5m2_connect or ""
    if effective_a5m2_cmd and effective_a5m2_connect:
        logger.info(f"DB検証: A5M2cmd ({effective_a5m2_cmd})")

    # ブラウザ設定
    context_opts = {
        "viewport": config.viewport,
        "locale": config.locale,
        "ignore_https_errors": config.ignore_https_errors,
    }
    if config.auth_type == "basic":
        context_opts["http_credentials"] = {
            "username": config.auth.get("username", ""),
            "password": config.auth.get("password", ""),
        }

    # ブラウザ起動
    total_ok = total_ng = total_skip = 0
    all_ng_details = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(**context_opts)
        if config.timeout:
            context.set_default_timeout(config.timeout)
        page = await context.new_page()

        # 認証処理
        if config.auth_type != "none":
            await authenticate(page, config)

        # シートごとにテスト実行
        for sheet_name in target_sheets:
            if sheet_name not in wb.sheetnames:
                logger.warning(f"シート '{sheet_name}' が見つかりません。スキップします。")
                continue

            ws = wb[sheet_name]

            # テスト日を記入（日付セルが設定で指定されている場合）
            date_cell = config.excel_date_cell
            if date_cell:
                ws[date_cell] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            ok, ng, skip, ng_details = await run_sheet(
                page, ws, config, screenshot_dir,
                effective_a5m2_cmd, effective_a5m2_connect,
                sheet_name, step_filter,
            )
            total_ok += ok
            total_ng += ng
            total_skip += skip
            all_ng_details.extend(ng_details)

            logger.info(f"[{sheet_name}] 結果: {ok} OK, {ng} NG, {skip} SKIP")

        await browser.close()

    # ワークブックを保存
    wb.save(str(output_path))
    logger.info(f"エビデンスを保存しました: {output_path}")

    total = total_ok + total_ng + total_skip
    logger.info(f"全体結果: {total_ok}/{total} OK, {total_ng}/{total} NG, {total_skip}/{total} SKIP")

    # NG一覧をまとめて出力
    if all_ng_details:
        logger.info("--- NG一覧 ---")
        for ng_item in all_ng_details:
            logger.info(f"  [{ng_item['sheet']}] Step {ng_item['step_no']}: "
                        f"{ng_item['item']} → {ng_item['message']}")
        logger.info(f"--- NG {len(all_ng_details)} 件 ---")

    logger.info(f"ログ: {log_path}")

    # JSON結果レポート出力
    if json_report:
        report = {
            "spec": str(spec_path),
            "output": str(output_path),
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total": total, "ok": total_ok,
                "ng": total_ng, "skip": total_skip,
            },
            "ng_details": all_ng_details,
        }
        Path(json_report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"JSONレポート: {json_report}")

    return total_ok, total_ng, total_skip


def _setup_logging(log_path: Path):
    """コンソール + ファイルの両方にログを出力する."""
    logger.setLevel(logging.DEBUG)
    # 既存ハンドラをクリア（多重追加防止）
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    # コンソール出力
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # ファイル出力
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8", mode="w")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="テストエビデンス自動化ツール - Excel仕様書からテスト実行+エビデンス生成"
    )
    parser.add_argument("spec", help="テスト仕様書Excelファイルのパス")
    parser.add_argument("-o", "--output", help="エビデンス出力先のパス")
    parser.add_argument(
        "-c", "--config",
        help="プロジェクト設定ファイル（YAML）のパス",
    )
    parser.add_argument(
        "--sheets", nargs="+",
        help="実行対象のシート名（複数指定可。省略時は設定ファイルまたは全シート）",
    )
    parser.add_argument(
        "--a5m2-cmd",
        help="A5M2cmd.exe のパス（設定ファイルより優先）",
    )
    parser.add_argument(
        "--a5m2-connect",
        help="A5M2の接続文字列（設定ファイルより優先）",
    )
    parser.add_argument("--headed", action="store_true", help="ブラウザを表示して実行")
    parser.add_argument(
        "--steps",
        help="実行対象のステップ範囲（例: '1-5,10,15-20'）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仕様書の形式チェックのみ実行（ブラウザ起動なし）",
    )
    parser.add_argument(
        "--json-report",
        help="JSON結果レポートの出力先パス",
    )

    args = parser.parse_args()
    asyncio.run(run_tests(
        spec_path=args.spec,
        output_path=args.output,
        config_path=args.config,
        a5m2_cmd=args.a5m2_cmd,
        a5m2_connect=args.a5m2_connect,
        headless=not args.headed,
        sheets=args.sheets,
        step_range=args.steps,
        dry_run=args.dry_run,
        json_report=args.json_report,
    ))


if __name__ == "__main__":
    main()
