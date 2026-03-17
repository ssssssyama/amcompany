"""record2spec.py のユニットテスト."""

from pathlib import Path

import pytest
import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from record2spec import parse_playwright_script, convert_to_yaml_spec, record2spec


class TestParsePlaywrightScript:
    """Playwrightスクリプトのパース処理テスト."""

    def test_goto(self):
        steps = parse_playwright_script('page.goto("http://localhost:5000")')
        assert len(steps) == 1
        assert steps[0]["action"] == "navigate"
        assert steps[0]["input"] == "http://localhost:5000"

    def test_click(self):
        steps = parse_playwright_script('page.click("#submit-btn")')
        assert len(steps) == 1
        assert steps[0]["action"] == "click"
        assert steps[0]["selector"] == "#submit-btn"

    def test_locator_click(self):
        steps = parse_playwright_script('page.locator("#submit-btn").click()')
        assert len(steps) == 1
        assert steps[0]["action"] == "click"

    def test_fill(self):
        steps = parse_playwright_script('page.fill("#username", "admin")')
        assert len(steps) == 1
        assert steps[0]["action"] == "input"
        assert steps[0]["selector"] == "#username"
        assert steps[0]["input"] == "admin"

    def test_locator_fill(self):
        steps = parse_playwright_script('page.locator("#username").fill("admin")')
        assert len(steps) == 1
        assert steps[0]["action"] == "input"

    def test_select_option(self):
        steps = parse_playwright_script('page.select_option("#priority", "high")')
        assert len(steps) == 1
        assert steps[0]["action"] == "select"
        assert steps[0]["input"] == "high"

    def test_keyboard_press(self):
        steps = parse_playwright_script('page.keyboard.press("Enter")')
        assert len(steps) == 1
        assert steps[0]["action"] == "keyboard"
        assert steps[0]["input"] == "Enter"

    def test_press_with_selector(self):
        steps = parse_playwright_script('page.press("#input", "Enter")')
        assert len(steps) == 1
        assert steps[0]["action"] == "keyboard"
        assert steps[0]["input"] == "Enter"

    def test_hover(self):
        steps = parse_playwright_script('page.hover(".menu-item")')
        assert len(steps) == 1
        assert steps[0]["action"] == "hover"
        assert steps[0]["selector"] == ".menu-item"

    def test_upload(self):
        steps = parse_playwright_script('page.set_input_files("#file-input", "doc.pdf")')
        assert len(steps) == 1
        assert steps[0]["action"] == "upload"
        assert steps[0]["input"] == "doc.pdf"

    def test_expect_visible(self):
        steps = parse_playwright_script(
            'expect(page.locator("#dashboard")).to_be_visible()'
        )
        assert len(steps) == 1
        assert steps[0]["verify"] == "visible"
        assert steps[0]["target"] == "#dashboard"

    def test_expect_text(self):
        steps = parse_playwright_script(
            'expect(page.locator("#msg")).to_have_text("Success")'
        )
        assert len(steps) == 1
        assert steps[0]["verify"] == "text"
        assert steps[0]["expected"] == "Success"

    def test_empty_script(self):
        assert parse_playwright_script("") == []
        assert parse_playwright_script("# comment\nimport something") == []

    def test_multi_step_script(self):
        script = """
page.goto("http://localhost:5000")
page.fill("#username", "admin")
page.fill("#password", "pass123")
page.click("#login-btn")
"""
        steps = parse_playwright_script(script)
        assert len(steps) == 4
        assert steps[0]["action"] == "navigate"
        assert steps[1]["action"] == "input"
        assert steps[2]["action"] == "input"
        assert steps[3]["action"] == "click"


class TestConvertToYamlSpec:
    """YAML構造変換テスト."""

    def test_basic_conversion(self):
        steps = [{"action": "navigate", "input": "http://example.com"}]
        spec = convert_to_yaml_spec(steps, project="Test", sheet_name="Login")
        assert spec["project"] == "Test"
        assert len(spec["sheets"]) == 1
        assert spec["sheets"][0]["name"] == "Login"

    def test_screenshot_auto_insert_after_navigate(self):
        steps = [{"action": "navigate", "input": "http://example.com"}]
        spec = convert_to_yaml_spec(steps)
        enriched = spec["sheets"][0]["steps"]
        # navigate + auto screenshot + (末尾screenshotは navigate後と同じなので追加されない)
        assert any(s.get("verify") == "screenshot" for s in enriched)

    def test_screenshot_appended_at_end(self):
        steps = [{"action": "click", "selector": "#btn"}]
        spec = convert_to_yaml_spec(steps)
        enriched = spec["sheets"][0]["steps"]
        assert enriched[-1].get("verify") == "screenshot"


class TestRecord2Spec:
    """E2Eテスト: スクリプト → YAML ファイル生成."""

    def test_generates_yaml(self, tmp_path):
        script_file = tmp_path / "recorded.py"
        script_file.write_text("""
page.goto("http://localhost:5000")
page.fill("#username", "admin")
page.click("#login-btn")
""", encoding="utf-8")

        output_file = tmp_path / "output.yaml"
        record2spec(str(script_file), str(output_file), project="Test")

        assert output_file.exists()
        with open(output_file, encoding="utf-8") as f:
            spec = yaml.safe_load(f)
        assert spec["project"] == "Test"
        assert len(spec["sheets"][0]["steps"]) > 0

    def test_missing_file_exits(self):
        with pytest.raises(SystemExit):
            record2spec("/nonexistent/script.py")
