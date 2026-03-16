"""gen_spec.py のユニットテスト."""

import tempfile
from pathlib import Path

import pytest
import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gen_spec import normalize_step, validate_steps, gen_spec


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
