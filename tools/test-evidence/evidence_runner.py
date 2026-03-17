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

from gen_spec import _interpret_natural_language
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


def _resolve_runtime(text: str, runtime_vars: dict) -> str:
    """ランタイム変数 ${captured:xxx} を実行時に解決する."""
    if not text or "${captured:" not in text:
        return text

    def replacer(m):
        return runtime_vars.get(m.group(1), m.group(0))

    return re.sub(r"\$\{captured:([\w]+)\}", replacer, text)


def read_test_steps(ws, config: ProjectConfig) -> list[TestStep]:
    """テスト仕様書シートからテストステップを読み取る.

    config の excel セクションで列マッピング・ヘッダー行を制御可能。
    セレクタ・入力値・期待値等の ${変数名} を設定ファイルの値で置換する。
    """
    resolve = config.resolve
    col_map = config.excel_columns
    data_start = config.excel_data_start_row

    aliases = config.selector_aliases
    steps = []
    for row in range(data_start, ws.max_row + 1):
        no = ws[f"{col_map['no']}{row}"].value
        if no is None:
            continue

        action_raw = ws[f"{col_map['action']}{row}"].value
        verify_raw = ws[f"{col_map['verify_type']}{row}"].value
        selector_raw = ws[f"{col_map['selector']}{row}"].value or ""
        input_raw = ws[f"{col_map['input']}{row}"].value
        verify_target_raw = ws[f"{col_map['verify_target']}{row}"].value or ""
        expected_raw = ws[f"{col_map['expected']}{row}"].value
        item_raw = ws[f"{col_map['item']}{row}"].value or ""

        # action/verify が空なら item 欄の自然言語を解釈
        if not action_raw and not verify_raw:
            interpreted = _interpret_natural_language(
                {"item": item_raw}, aliases)
            action_raw = interpreted.get("action", action_raw)
            verify_raw = interpreted.get("verify",
                                         interpreted.get("verify_type", verify_raw))
            selector_raw = interpreted.get("selector", selector_raw)
            if "input" in interpreted and interpreted["input"] != item_raw:
                input_raw = interpreted["input"]
            verify_target_raw = interpreted.get("target", verify_target_raw)
            expected_raw = interpreted.get("expected", expected_raw)

        step = TestStep(
            row=row,
            no=no,
            item=item_raw,
            action=action_raw,
            selector=resolve(selector_raw),
            input_val=resolve(
                str(input_raw) if input_raw is not None else ""
            ),
            verify_type=verify_raw,
            verify_target=resolve(verify_target_raw),
            expected=resolve(
                str(expected_raw) if expected_raw is not None else ""
            ),
            note=ws[f"{col_map['note']}{row}"].value,
        )
        steps.append(step)
    return steps


async def execute_action(page, step: TestStep, *,
                         context=None, pages: dict | None = None,
                         runtime_vars: dict | None = None,
                         active_frame=None, download_dir: Path | None = None):
    """ブラウザ操作を実行する.

    Returns:
        dict | None: 状態変更情報。キー例:
            - "active_frame": iframe切替 (None=メインに戻る)
            - "switch_page": タブ切替先のページ名
            - "new_page": (名前, Page) 新タブ情報
            - "close_page": 閉じるタブ名
            - "download_path": ダウンロードされたファイルパス
    """
    action = step.action
    # iframe内操作: active_frame がセットされていれば locator 経由で操作
    target = active_frame if active_frame else page
    result = {}

    if action == "navigate":
        await page.goto(step.input_val, wait_until="networkidle")

    elif action == "click":
        if active_frame:
            await active_frame.locator(step.selector).click()
        else:
            await page.click(step.selector)
        await page.wait_for_load_state("networkidle")

    elif action == "input":
        if active_frame:
            await active_frame.locator(step.selector).fill(step.input_val)
        else:
            await page.fill(step.selector, step.input_val)

    elif action == "select":
        if active_frame:
            await active_frame.locator(step.selector).select_option(step.input_val)
        else:
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
        if active_frame:
            await active_frame.locator(step.selector).wait_for(
                state=wait_state, timeout=wait_timeout)
        else:
            await page.wait_for_selector(
                step.selector, state=wait_state, timeout=wait_timeout)

    elif action == "upload":
        if active_frame:
            await active_frame.locator(step.selector).set_input_files(step.input_val)
        else:
            await page.set_input_files(step.selector, step.input_val)

    elif action == "hover":
        if active_frame:
            await active_frame.locator(step.selector).hover()
        else:
            await page.hover(step.selector)

    elif action == "scroll":
        if step.selector:
            if active_frame:
                await active_frame.locator(step.selector).scroll_into_view_if_needed()
            else:
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
        # iframe 永続切替: input="main" でメインフレームに戻る
        if step.input_val and step.input_val.strip().lower() == "main":
            result["active_frame"] = None
        else:
            result["active_frame"] = page.frame_locator(step.selector)

    elif action == "capture":
        # 画面要素のテキスト/属性値をランタイム変数に保存
        var_spec = step.input_val.strip()
        var_name = var_spec
        attr_name = None
        if ":attr=" in var_spec:
            var_name, attr_part = var_spec.split(":attr=", 1)
            attr_name = attr_part.strip()
        if active_frame:
            loc = active_frame.locator(step.selector)
            if attr_name:
                captured_val = await loc.get_attribute(attr_name) or ""
            else:
                captured_val = (await loc.text_content() or "").strip()
        else:
            element = await page.query_selector(step.selector)
            if element is None:
                raise RuntimeError(f"capture: 要素が見つかりません: {step.selector}")
            if attr_name:
                captured_val = await element.get_attribute(attr_name) or ""
            else:
                captured_val = (await element.text_content() or "").strip()
        if runtime_vars is not None:
            runtime_vars[var_name] = captured_val
        logger.debug(f"  capture: ${{{var_name}}} = '{captured_val}'")

    elif action == "new_tab":
        # クリックで開かれる新タブをキャプチャ、またはURLで新タブを開く
        tab_name = step.input_val.strip() if step.input_val else "tab"
        if step.selector:
            # セレクタをクリックして開かれるタブをキャプチャ
            async with context.expect_page() as new_page_info:
                if active_frame:
                    await active_frame.locator(step.selector).click()
                else:
                    await page.click(step.selector)
            new_page = await new_page_info.value
            await new_page.wait_for_load_state("networkidle")
        else:
            # URLを指定して新タブを開く（input_valがタブ名の場合はnoteにURLを記載）
            new_page = await context.new_page()
            if step.note and step.note.startswith("http"):
                await new_page.goto(step.note, wait_until="networkidle")
        result["new_page"] = (tab_name, new_page)

    elif action == "switch_tab":
        tab_name = step.input_val.strip() if step.input_val else "main"
        result["switch_page"] = tab_name

    elif action == "close_tab":
        tab_name = step.input_val.strip() if step.input_val else ""
        if tab_name:
            result["close_page"] = tab_name

    elif action == "download":
        # ファイルダウンロードを待機
        dl_dir = download_dir or Path(tempfile.mkdtemp())
        async with page.expect_download() as download_info:
            if active_frame:
                await active_frame.locator(step.selector).click()
            else:
                await page.click(step.selector)
        download = await download_info.value
        save_name = step.input_val.strip() if step.input_val else download.suggested_filename
        save_path = dl_dir / save_name
        await download.save_as(str(save_path))
        result["download_path"] = save_path
        logger.debug(f"  download: {save_path}")

    elif action == "include":
        # 別シートの共通手順を参照実行（run_sheet側で処理するためここではpass）
        pass

    else:
        logger.warning(f"未知の操作種別: {action}")

    return result or None


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


def verify_download(download_path: Path | None, step: TestStep) -> tuple[bool, str]:
    """ダウンロードされたファイルを検証する."""
    if download_path is None or not download_path.exists():
        return False, f"NG: ダウンロードファイルが見つかりません: {step.verify_target}"
    if not step.expected:
        return True, f"OK: ファイルが存在します: {download_path.name}"
    try:
        content = download_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return False, f"NG: ファイル読み取りエラー: {e}"
    return _match_expected(content, step.expected)


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


def _parse_retry_from_note(note: str) -> tuple[int, int]:
    """備考欄から retry:N / retry_wait:N を解析する.

    Returns:
        (retry_count, retry_wait_ms)
    """
    retry = 0
    retry_wait = 1000
    if not note:
        return retry, retry_wait
    for part in note.split():
        if part.startswith("retry:"):
            try:
                retry = int(part.split(":", 1)[1])
            except ValueError:
                pass
        elif part.startswith("retry_wait:"):
            try:
                retry_wait = int(part.split(":", 1)[1])
            except ValueError:
                pass
    return retry, retry_wait


async def run_sheet(page, ws, config: ProjectConfig, screenshot_dir: Path,
                    effective_a5m2_cmd: str, effective_a5m2_connect: str,
                    sheet_name: str,
                    step_filter: set[int] | None = None,
                    wb=None, context=None) -> tuple[int, int, int, list]:
    """1シート分のテストを実行する.

    拡張機能:
    - ランタイム変数: capture で取得した値を ${captured:xxx} で後続ステップから参照
    - 複数タブ: new_tab/switch_tab/close_tab で複数ページを管理
    - iframe永続: iframe で切替え、iframe input=main で戻る
    - 条件分岐: if_ok/if_ng で前ステップの結果に応じて実行/スキップ
    - リトライ: 備考欄に retry:N を記載するとN回まで再試行

    Args:
        step_filter: 実行対象のステップNo.集合（Noneなら全ステップ実行）
        wb: ワークブック（action=includeで別シート参照時に使用）
        context: ブラウザコンテキスト（複数タブ管理用）

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

    # 拡張: ランタイム変数、ページ管理、iframe永続
    runtime_vars = {}
    pages = {"main": page}
    current_page_name = "main"
    active_frame = None
    last_download_path = None  # 直近のダウンロードファイルパス

    aborted = False
    prev_passed = None  # 前ステップの結果（条件分岐用）
    ng_details = []  # NG一覧を収集

    for idx, step in enumerate(steps, 1):
        step_start = time.monotonic()

        # ランタイム変数をステップの各フィールドに適用
        step.selector = _resolve_runtime(step.selector, runtime_vars)
        step.input_val = _resolve_runtime(step.input_val, runtime_vars)
        step.verify_target = _resolve_runtime(step.verify_target, runtime_vars)
        step.expected = _resolve_runtime(step.expected, runtime_vars)

        logger.info(f"  [{idx}/{total_steps}] Step {step.no}: {step.item}...")

        screenshot_path = None
        passed = None
        message = ""
        current_page = pages.get(current_page_name, page)

        # 条件分岐: if_ok / if_ng
        if step.action in ("if_ok", "if_ng"):
            should_run = (step.action == "if_ok" and prev_passed is True) or \
                         (step.action == "if_ng" and prev_passed is False)
            if not should_run:
                passed = None
                cond = "OK" if step.action == "if_ok" else "NG"
                message = f"条件スキップ (前ステップが{cond}ではない)"
                write_result(ws, col_map, step, passed, message, None, img_w, img_h)
                elapsed = time.monotonic() - step_start
                logger.info(f"  [{idx}/{total_steps}] Step {step.no}: [SKIP] {message} ({elapsed:.1f}s)")
                continue
            # 条件を満たした場合: input_val に実際のアクション名が入る
            # selector はそのまま使用
            step.action = step.input_val.strip().lower() if step.input_val else ""
            if not step.action:
                passed = None
                message = "条件分岐: 実行するアクションが未指定"
                write_result(ws, col_map, step, passed, message, None, img_w, img_h)
                elapsed = time.monotonic() - step_start
                logger.info(f"  [{idx}/{total_steps}] Step {step.no}: [SKIP] {message} ({elapsed:.1f}s)")
                continue

        # action=include: 別シートの共通手順を参照実行
        if step.action == "include":
            ref_sheet = step.input_val.strip()
            if wb is None or ref_sheet not in wb.sheetnames:
                passed = False
                message = f"includeエラー: シート '{ref_sheet}' が見つかりません"
                write_result(ws, col_map, step, passed, message, None, img_w, img_h)
                elapsed = time.monotonic() - step_start
                logger.info(f"  [{idx}/{total_steps}] Step {step.no}: [NG] {message} ({elapsed:.1f}s)")
                ng_details.append({"sheet": sheet_name, "step_no": step.no,
                                   "item": step.item, "message": message})
                if on_fail == "abort":
                    aborted = True
                prev_passed = passed
                continue
            logger.info(f"  → include: シート '{ref_sheet}' のステップを実行")
            ref_ws = wb[ref_sheet]
            ref_steps = read_test_steps(ref_ws, config)
            for ref_step in ref_steps:
                try:
                    if ref_step.action and ref_step.action != "skip":
                        await execute_action(current_page, ref_step,
                                             context=context, pages=pages,
                                             runtime_vars=runtime_vars,
                                             active_frame=active_frame)
                    if ref_step.verify_type == "db":
                        if config.db_type == "sqlite" and config.sqlite_path:
                            r_passed, r_msg = verify_db_sqlite(ref_step, config.sqlite_path)
                        else:
                            r_passed, r_msg = verify_db_a5m2(
                                ref_step, effective_a5m2_cmd, effective_a5m2_connect)
                        if not r_passed:
                            raise RuntimeError(f"include内DB検証NG: {r_msg}")
                    elif ref_step.verify_type and ref_step.verify_type != "screenshot":
                        r_passed, r_msg = await verify_screen(current_page, ref_step)
                        if not r_passed:
                            raise RuntimeError(f"include内検証NG: {r_msg}")
                except Exception as e:
                    passed = False
                    message = f"includeエラー ({ref_sheet}): {e}"
                    write_result(ws, col_map, step, passed, message, None, img_w, img_h)
                    elapsed = time.monotonic() - step_start
                    logger.info(f"  [{idx}/{total_steps}] Step {step.no}: [NG] {message} ({elapsed:.1f}s)")
                    ng_details.append({"sheet": sheet_name, "step_no": step.no,
                                       "item": step.item, "message": message})
                    if on_fail == "abort":
                        aborted = True
                    break
            else:
                passed = True
                message = f"OK: include '{ref_sheet}' ({len(ref_steps)}ステップ)"
                write_result(ws, col_map, step, passed, message, None, img_w, img_h)
                elapsed = time.monotonic() - step_start
                logger.info(f"  [{idx}/{total_steps}] Step {step.no}: [OK] {message} ({elapsed:.1f}s)")
            prev_passed = passed
            continue

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

        # リトライ設定を備考欄から解析
        retry_count, retry_wait = _parse_retry_from_note(step.note)

        for attempt in range(1 + retry_count):
            if attempt > 0:
                logger.info(f"  → リトライ {attempt}/{retry_count} ({retry_wait}ms待機後)")
                await asyncio.sleep(retry_wait / 1000)

            try:
                # ブラウザ操作を実行
                action_result = None
                if step.action:
                    action_result = await execute_action(
                        current_page, step,
                        context=context, pages=pages,
                        runtime_vars=runtime_vars,
                        active_frame=active_frame,
                        download_dir=screenshot_dir.parent / "downloads",
                    )

                # execute_action の戻り値による状態更新
                if action_result:
                    if "active_frame" in action_result:
                        active_frame = action_result["active_frame"]
                    if "new_page" in action_result:
                        tab_name, new_pg = action_result["new_page"]
                        pages[tab_name] = new_pg
                        current_page_name = tab_name
                        current_page = new_pg
                        logger.debug(f"  new_tab: '{tab_name}' を追加")
                    if "switch_page" in action_result:
                        target_name = action_result["switch_page"]
                        if target_name in pages:
                            current_page_name = target_name
                            current_page = pages[target_name]
                            active_frame = None  # タブ切替時はiframeリセット
                            logger.debug(f"  switch_tab: '{target_name}' に切替")
                        else:
                            raise RuntimeError(
                                f"switch_tab: タブ '{target_name}' が見つかりません "
                                f"(利用可能: {list(pages.keys())})")
                    if "close_page" in action_result:
                        close_name = action_result["close_page"]
                        if close_name in pages and close_name != "main":
                            await pages[close_name].close()
                            del pages[close_name]
                            if current_page_name == close_name:
                                current_page_name = "main"
                                current_page = pages["main"]
                                active_frame = None
                            logger.debug(f"  close_tab: '{close_name}' を閉じた")
                    if "download_path" in action_result:
                        last_download_path = action_result["download_path"]

                # スクリーンショット撮影
                if step.action or step.verify_type == "screenshot":
                    screenshot_path = await take_screenshot(
                        current_page, screenshot_dir, f"{sheet_name}_{step.no}",
                    )

                # 検証
                if step.verify_type == "download":
                    passed, message = verify_download(last_download_path, step)
                elif step.verify_type == "db":
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
                    passed, message = await verify_screen(current_page, step)
                else:
                    passed = True
                    message = "操作完了"

            except Exception as e:
                passed = False
                message = f"エラー: {e}"
                logger.debug(f"  Step {step.no} 例外詳細:\n{traceback.format_exc()}")
                try:
                    screenshot_path = await take_screenshot(
                        current_page, screenshot_dir,
                        f"{sheet_name}_{step.no}_error",
                    )
                except Exception:
                    pass

            # リトライ: 成功したらループ脱出
            if passed is not False:
                break
            # まだリトライ回数が残っていれば続行
            if attempt < retry_count:
                logger.info(f"  Step {step.no}: [NG] {message} → リトライします")

        if attempt > 0 and passed:
            message = f"{message} (リトライ{attempt}回目で成功)"

        # 結果をExcelに書き込み
        write_result(ws, col_map, step, passed, message, screenshot_path, img_w, img_h)

        elapsed = time.monotonic() - step_start
        status = "OK" if passed else ("NG" if passed is False else "SKIP")
        logger.info(f"  [{idx}/{total_steps}] Step {step.no}: [{status}] {message} ({elapsed:.1f}s)")

        prev_passed = passed

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

    # 開いた追加タブをクリーンアップ（mainは除く）
    for tab_name, tab_page in list(pages.items()):
        if tab_name != "main":
            try:
                await tab_page.close()
            except Exception:
                pass

    # サマリー集計
    ok = sum(1 for s in steps if ws[f"{col_map['result']}{s.row}"].value == "OK")
    ng = sum(1 for s in steps if ws[f"{col_map['result']}{s.row}"].value == "NG")
    skip = sum(1 for s in steps if ws[f"{col_map['result']}{s.row}"].value == "SKIP")
    return ok, ng, skip, ng_details


def _run_setup_teardown_sql(db_path: str, sql: str, label: str):
    """setup_sql / teardown_sql を SQLite に対して実行する."""
    import sqlite3 as _sqlite3
    try:
        conn = _sqlite3.connect(db_path)
        conn.executescript(sql)
        conn.close()
        logger.info(f"  {label}: 実行完了")
    except Exception as e:
        logger.warning(f"  {label}: エラー: {e}")


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

    基本的な構文チェックに加え、以下の拡張チェックも実行する:
    - action=include の参照先シート存在確認
    - verify_type=db のSQL構文チェック（SQLite接続可能時のみ）
    - 期待値プレフィックスの妥当性チェック

    Returns:
        エラーメッセージのリスト（空なら問題なし）
    """
    valid_actions = {
        "navigate", "click", "input", "select", "wait", "wait_for",
        "upload", "hover", "scroll", "keyboard",
        "alert_accept", "alert_dismiss", "iframe", "include", "skip",
        "capture", "new_tab", "switch_tab", "close_tab", "download",
        "if_ok", "if_ng", "",
    }
    valid_verify_types = {
        "text", "value", "visible", "hidden", "url", "screenshot", "db",
        "download", "",
    }
    valid_expected_prefixes = {
        "contains:", "regex:",
        "empty", "not_empty",
        "rowcount:", "rows:", "rows_any:", "rows_all:", "values:",
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

            # include: 参照先シートの存在確認
            if step.action == "include":
                ref_sheet = step.input_val.strip()
                if not ref_sheet:
                    errors.append(f"{prefix}: action='include' にシート名が未指定")
                elif ref_sheet not in wb.sheetnames:
                    errors.append(f"{prefix}: include先シート '{ref_sheet}' が存在しません")

            # DB検証: SQL構文チェック（SQLite利用時のみ）
            if step.verify_type == "db" and step.verify_target:
                if config.db_type == "sqlite" and config.sqlite_path:
                    import sqlite3 as _sqlite3
                    db_path = config.sqlite_path
                    if Path(db_path).exists():
                        try:
                            conn = _sqlite3.connect(db_path)
                            conn.execute(f"EXPLAIN {step.verify_target}")
                            conn.close()
                        except _sqlite3.Error as e:
                            errors.append(f"{prefix}: SQL構文エラー: {e}")

            # 期待値プレフィックスの妥当性チェック
            if step.expected:
                exp = step.expected
                has_valid_prefix = False
                # プレフィックスなし（完全一致）も有効
                if not any(exp.startswith(p) for p in valid_expected_prefixes):
                    # 完全一致として扱う → 常に有効
                    has_valid_prefix = True
                else:
                    has_valid_prefix = True
                # DB検証で画面系プレフィックスを使っている場合は警告
                if step.verify_type == "db" and exp.startswith("regex:"):
                    errors.append(
                        f"{prefix}: verify_type='db' に 'regex:' プレフィックスは"
                        "使用できません（1行目1列目の正規表現マッチは対応していますが意図的ですか？）"
                    )

    return errors


async def run_tests(spec_path: str, output_path: str | None = None,
                    config_path: str | None = None,
                    a5m2_cmd: str | None = None,
                    a5m2_connect: str | None = None,
                    headless: bool = True,
                    sheets: list[str] | None = None,
                    step_range: str | None = None,
                    dry_run: bool = False,
                    verify_selectors: bool = False,
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
        verify_selectors: Trueならブラウザを起動してセレクタの存在を確認する
        json_report: JSON結果レポートの出力先パス
    """
    # プロジェクト設定を読み込み
    config = ProjectConfig(config_path)

    spec_path = Path(spec_path)

    # 出力先ディレクトリの決定（設定ファイル > デフォルト）
    if output_path is None:
        out_dir = config.output_dir
        if out_dir:
            out_dir = Path(out_dir)
            if config.output_timestamp:
                out_dir = out_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = out_dir / f"{spec_path.stem}_evidence{spec_path.suffix}"
        else:
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

    # セレクタ検証モード: ブラウザを起動して各セレクタの存在を確認
    if verify_selectors:
        logger.info("セレクタ検証モード: 各ステップのセレクタを確認")
        selector_errors = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                viewport=config.viewport, locale=config.locale,
                ignore_https_errors=config.ignore_https_errors,
            )
            if config.timeout:
                context.set_default_timeout(config.timeout)
            page = await context.new_page()

            if config.auth_type != "none":
                await authenticate(page, config)

            for sname in target_sheets:
                if sname not in wb.sheetnames:
                    continue
                steps = read_test_steps(wb[sname], config)
                current_url = None
                for step in steps:
                    # navigateでページ遷移
                    if step.action == "navigate" and step.input_val:
                        try:
                            await page.goto(step.input_val, wait_until="networkidle")
                            current_url = step.input_val
                        except Exception as e:
                            selector_errors.append(
                                f"[{sname}] Step {step.no}: navigate失敗: {e}")
                        continue
                    # セレクタを持つステップの検証
                    sel = step.selector or (
                        step.verify_target if step.verify_type in (
                            "text", "value", "visible", "hidden") else "")
                    if sel and current_url:
                        element = await page.query_selector(sel)
                        if element is None:
                            selector_errors.append(
                                f"[{sname}] Step {step.no}: セレクタ '{sel}' が見つかりません")
                        else:
                            logger.info(f"  [{sname}] Step {step.no}: '{sel}' → OK")

            await browser.close()

        if selector_errors:
            for err in selector_errors:
                logger.error(f"  {err}")
            logger.info(f"セレクタ検証結果: {len(selector_errors)} 件のエラー")
        else:
            logger.info("セレクタ検証結果: 全セレクタOK")
        return (0, 0, 0) if selector_errors else (1, 0, 0)

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

            # setup_sql: シート実行前にSQLを実行（SQLite利用時のみ）
            if config.setup_sql and config.db_type == "sqlite" and config.sqlite_path:
                _run_setup_teardown_sql(config.sqlite_path, config.setup_sql, "setup_sql")

            ok, ng, skip, ng_details = await run_sheet(
                page, ws, config, screenshot_dir,
                effective_a5m2_cmd, effective_a5m2_connect,
                sheet_name, step_filter, wb=wb, context=context,
            )
            total_ok += ok
            total_ng += ng
            total_skip += skip
            all_ng_details.extend(ng_details)

            # teardown_sql: シート実行後にSQLを実行（SQLite利用時のみ）
            if config.teardown_sql and config.db_type == "sqlite" and config.sqlite_path:
                _run_setup_teardown_sql(config.sqlite_path, config.teardown_sql, "teardown_sql")

            logger.info(f"[{sheet_name}] 結果: {ok} OK, {ng} NG, {skip} SKIP")

        await browser.close()

    # ワークブックを保存（既存ファイルがある場合はバックアップ）
    if output_path.exists():
        backup_path = output_path.parent / f"{output_path.stem}_backup{output_path.suffix}"
        try:
            shutil.copy2(output_path, backup_path)
            logger.debug(f"バックアップを作成: {backup_path}")
        except OSError as e:
            logger.warning(f"バックアップ作成に失敗（続行します）: {e}")
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
    """コンソール + ファイルの両方にログを出力する.

    ログファイルは追記モード（append）で、5MB超過時に最大3世代ローテーションする。
    """
    from logging.handlers import RotatingFileHandler

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

    # ファイル出力（ローテーション: 5MB x 3世代）
    file_handler = RotatingFileHandler(
        str(log_path), encoding="utf-8", mode="a",
        maxBytes=5 * 1024 * 1024, backupCount=3,
    )
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
        "--verify-selectors", action="store_true",
        help="ブラウザを起動して各ステップのセレクタ存在を事前確認",
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
        verify_selectors=args.verify_selectors,
        json_report=args.json_report,
    ))


if __name__ == "__main__":
    main()
