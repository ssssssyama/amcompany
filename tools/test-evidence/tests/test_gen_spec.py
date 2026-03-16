"""gen_spec.py のユニットテスト."""

import tempfile
from pathlib import Path

import pytest
import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gen_spec import normalize_step, validate_steps, gen_spec, _expand_data_source


class TestNormalizeStep:
    """YAML短縮記法の正規化テスト."""

    def test_basic_action(self):
        step = normalize_step({"action": "click", "selector": "#btn"}, 1)
        assert step["no"] == 1
        assert step["action"] == "click"
        assert step["selector"] == "#btn"
        assert step["item"] == "click: #btn"

    def test_navigate_auto_item(self):
        step = normalize_step({"action": "navigate", "input": "http://example.com"}, 1)
        assert step["action"] == "navigate"
        assert step["input"] == "http://example.com"
        assert step["item"] == "ページを開く"

    def test_include_shorthand(self):
        step = normalize_step({"action": "include", "sheet": "共通ログイン"}, 1)
        assert step["action"] == "include"
        assert step["input"] == "共通ログイン"
        assert "共通ログイン" in step["item"]

    def test_verify_shorthand(self):
        step = normalize_step({
            "verify": "text", "target": "#msg", "expected": "OK"
        }, 1)
        assert step["verify_type"] == "text"
        assert step["verify_target"] == "#msg"
        assert step["expected"] == "OK"

    def test_verify_db_shorthand(self):
        step = normalize_step({
            "verify": "db", "sql": "SELECT COUNT(*) FROM t", "expected": "rowcount:3"
        }, 1)
        assert step["verify_type"] == "db"
        assert step["verify_target"] == "SELECT COUNT(*) FROM t"
        assert step["expected"] == "rowcount:3"

    def test_explicit_item(self):
        step = normalize_step({
            "action": "click", "selector": "#btn", "item": "送信ボタン押下"
        }, 1)
        assert step["item"] == "送信ボタン押下"

    def test_verify_target_fallback(self):
        """verify短縮記法でverify_targetキーを使った場合のフォールバック."""
        step = normalize_step({
            "verify": "text", "verify_target": "#welcome-msg", "expected": "OK"
        }, 1)
        assert step["verify_target"] == "#welcome-msg"

    def test_longform_verify(self):
        """verify短縮記法を使わず、verify_type/verify_target で指定."""
        step = normalize_step({
            "verify_type": "visible", "verify_target": "#dashboard"
        }, 1)
        assert step["verify_type"] == "visible"
        assert step["verify_target"] == "#dashboard"


class TestValidateSteps:
    """テストステップのバリデーションテスト."""

    def test_valid_steps(self):
        steps = [
            {"action": "navigate", "input": "http://example.com"},
            {"action": "click", "selector": "#btn"},
            {"verify": "text", "target": "#msg"},
        ]
        errors = validate_steps("Sheet1", steps)
        assert errors == []

    def test_invalid_action(self):
        errors = validate_steps("Sheet1", [{"action": "invalid_action"}])
        assert len(errors) == 1
        assert "無効な操作種別" in errors[0]

    def test_invalid_verify_type(self):
        errors = validate_steps("Sheet1", [{"verify": "invalid_verify"}])
        assert len(errors) == 1
        assert "無効な検証種別" in errors[0]

    def test_click_without_selector(self):
        errors = validate_steps("Sheet1", [{"action": "click"}])
        assert len(errors) == 1
        assert "セレクタが未指定" in errors[0]

    def test_navigate_without_input(self):
        errors = validate_steps("Sheet1", [{"action": "navigate"}])
        assert len(errors) == 1
        assert "URLが未指定" in errors[0]

    def test_include_without_sheet(self):
        errors = validate_steps("Sheet1", [{"action": "include"}])
        assert len(errors) == 1
        assert "シート名が未指定" in errors[0]

    def test_include_with_sheet_is_valid(self):
        errors = validate_steps("Sheet1", [
            {"action": "include", "sheet": "共通手順"}
        ])
        assert errors == []


class TestGenSpec:
    """gen_spec関数のE2Eテスト."""

    def test_generates_xlsx(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml.dump({
            "project": "テスト",
            "sheets": [{
                "name": "Sheet1",
                "steps": [
                    {"action": "navigate", "input": "http://example.com"},
                    {"action": "click", "selector": "#btn", "item": "ボタン押下"},
                ],
            }],
        }, allow_unicode=True), encoding="utf-8")

        output_file = tmp_path / "test.xlsx"
        gen_spec(str(yaml_file), str(output_file))
        assert output_file.exists()
        assert output_file.stat().st_size > 0

    def test_validation_error_exits(self, tmp_path):
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(yaml.dump({
            "sheets": [{
                "name": "Sheet1",
                "steps": [{"action": "invalid_action"}],
            }],
        }, allow_unicode=True), encoding="utf-8")

        with pytest.raises(SystemExit):
            gen_spec(str(yaml_file))

    def test_missing_file_exits(self):
        with pytest.raises(SystemExit):
            gen_spec("/nonexistent/file.yaml")

    def test_data_driven_csv(self, tmp_path):
        """data_source でCSVを指定するとステップが展開される."""
        csv_file = tmp_path / "users.csv"
        csv_file.write_text("name,email\n田中,tanaka@test.com\n鈴木,suzuki@test.com\n",
                            encoding="utf-8")
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml.dump({
            "project": "DDT",
            "sheets": [{
                "name": "ユーザー登録",
                "data_source": "users.csv",
                "steps": [
                    {"action": "input", "selector": "#name", "input": "${data:name}",
                     "item": "名前入力"},
                    {"action": "input", "selector": "#email", "input": "${data:email}",
                     "item": "メール入力"},
                ],
            }],
        }, allow_unicode=True), encoding="utf-8")

        output_file = tmp_path / "test.xlsx"
        gen_spec(str(yaml_file), str(output_file))
        assert output_file.exists()

        from openpyxl import load_workbook
        wb = load_workbook(str(output_file))
        ws = wb.active
        # 2名 × 2ステップ = 4行のデータ（7行目から開始）
        assert ws["A7"].value == 1
        assert ws["A10"].value == 4
        # ${data:name} が展開されている
        assert "田中" in (ws["E7"].value or "")
        assert "鈴木" in (ws["E9"].value or "")

    def test_data_driven_json(self, tmp_path):
        """data_source でJSONを指定するとステップが展開される."""
        import json
        json_file = tmp_path / "items.json"
        json_file.write_text(json.dumps([
            {"product": "商品A", "price": "1000"},
            {"product": "商品B", "price": "2000"},
            {"product": "商品C", "price": "3000"},
        ], ensure_ascii=False), encoding="utf-8")
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(yaml.dump({
            "project": "DDT",
            "sheets": [{
                "name": "商品登録",
                "data_source": "items.json",
                "steps": [
                    {"action": "input", "selector": "#product", "input": "${data:product}",
                     "item": "商品名入力"},
                ],
            }],
        }, allow_unicode=True), encoding="utf-8")

        output_file = tmp_path / "test.xlsx"
        gen_spec(str(yaml_file), str(output_file))

        from openpyxl import load_workbook
        wb = load_workbook(str(output_file))
        ws = wb.active
        # 3件 × 1ステップ = 3行
        assert ws["A9"].value == 3
        assert "商品C" in (ws["E9"].value or "")


class TestNormalizeStepExtended:
    """新アクションの正規化テスト."""

    def test_capture(self):
        step = normalize_step({"action": "capture", "selector": "#id", "input": "order_id"}, 1)
        assert step["action"] == "capture"
        assert step["input"] == "order_id"

    def test_new_tab(self):
        step = normalize_step({"action": "new_tab", "selector": "#link", "input": "report"}, 1)
        assert step["action"] == "new_tab"

    def test_switch_tab(self):
        step = normalize_step({"action": "switch_tab", "input": "main"}, 1)
        assert step["action"] == "switch_tab"

    def test_download(self):
        step = normalize_step({"action": "download", "selector": "#export"}, 1)
        assert step["action"] == "download"

    def test_if_ok(self):
        step = normalize_step({"action": "if_ok", "input": "click", "selector": "#next"}, 1)
        assert step["action"] == "if_ok"
        assert step["input"] == "click"

    def test_if_ng(self):
        step = normalize_step({"action": "if_ng", "input": "click", "selector": "#retry"}, 1)
        assert step["action"] == "if_ng"

    def test_retry_in_note(self):
        step = normalize_step({"action": "click", "selector": "#btn", "retry": 3}, 1)
        assert "retry:3" in step["note"]

    def test_retry_and_wait_in_note(self):
        step = normalize_step({"action": "click", "selector": "#btn",
                               "retry": 2, "retry_wait": 500}, 1)
        assert "retry:2" in step["note"]
        assert "retry_wait:500" in step["note"]

    def test_verify_download(self):
        step = normalize_step({"verify": "download", "target": "export.csv",
                               "expected": "contains:田中"}, 1)
        assert step["verify_type"] == "download"


class TestValidateStepsExtended:
    """新アクションのバリデーションテスト."""

    def test_capture_valid(self):
        errors = validate_steps("S", [{"action": "capture", "selector": "#id", "input": "var"}])
        assert errors == []

    def test_capture_no_selector(self):
        errors = validate_steps("S", [{"action": "capture", "input": "var"}])
        assert any("セレクタが未指定" in e for e in errors)

    def test_capture_no_input(self):
        errors = validate_steps("S", [{"action": "capture", "selector": "#id"}])
        assert any("変数名" in e for e in errors)

    def test_switch_tab_no_input(self):
        errors = validate_steps("S", [{"action": "switch_tab"}])
        assert any("タブ名" in e for e in errors)

    def test_download_no_selector(self):
        errors = validate_steps("S", [{"action": "download"}])
        assert any("セレクタが未指定" in e for e in errors)

    def test_new_actions_valid(self):
        steps = [
            {"action": "capture", "selector": "#x", "input": "v"},
            {"action": "new_tab", "selector": "#link", "input": "tab1"},
            {"action": "switch_tab", "input": "tab1"},
            {"action": "close_tab", "input": "tab1"},
            {"action": "download", "selector": "#dl"},
            {"action": "if_ok", "input": "click", "selector": "#btn"},
            {"action": "if_ng", "input": "click", "selector": "#retry"},
        ]
        errors = validate_steps("S", steps)
        assert errors == []


class TestExpandDataSource:
    """data_source 展開テスト."""

    def test_csv_expansion(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,email\nAlice,a@b.com\nBob,b@c.com\n",
                            encoding="utf-8")
        steps = [
            {"action": "input", "selector": "#name", "input": "${data:name}", "item": "名前"},
            {"action": "input", "selector": "#email", "input": "${data:email}", "item": "メール"},
        ]
        expanded = _expand_data_source(steps, "data.csv", tmp_path)
        assert len(expanded) == 4  # 2行 × 2ステップ
        assert expanded[0]["input"] == "Alice"
        assert expanded[1]["input"] == "a@b.com"
        assert expanded[2]["input"] == "Bob"
        assert expanded[3]["input"] == "b@c.com"
        # テスト項目名にrow番号が付与
        assert "[row1:" in expanded[0]["item"]
        assert "[row2:" in expanded[2]["item"]

    def test_json_expansion(self, tmp_path):
        import json as json_mod
        json_file = tmp_path / "data.json"
        json_file.write_text(json_mod.dumps([
            {"x": "1"}, {"x": "2"}, {"x": "3"}
        ]), encoding="utf-8")
        steps = [{"action": "input", "selector": "#x", "input": "${data:x}", "item": "入力"}]
        expanded = _expand_data_source(steps, "data.json", tmp_path)
        assert len(expanded) == 3
        assert expanded[0]["input"] == "1"
        assert expanded[2]["input"] == "3"

    def test_missing_file_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            _expand_data_source([], "missing.csv", tmp_path)

    def test_unresolved_var_unchanged(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a\n1\n", encoding="utf-8")
        steps = [{"action": "input", "selector": "#x", "input": "${data:missing}", "item": "test"}]
        expanded = _expand_data_source(steps, "data.csv", tmp_path)
        assert expanded[0]["input"] == "${data:missing}"
