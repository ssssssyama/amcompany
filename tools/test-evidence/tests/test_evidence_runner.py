"""evidence_runner.py の新機能ユニットテスト."""

import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evidence_runner import (
    _resolve_runtime,
    _parse_retry_from_note,
    verify_download,
    TestStep,
)


class TestResolveRuntime:
    """ランタイム変数 ${captured:xxx} の解決テスト."""

    def test_basic_substitution(self):
        vars_ = {"order_id": "ORD-123"}
        assert _resolve_runtime("${captured:order_id}", vars_) == "ORD-123"

    def test_multiple_vars(self):
        vars_ = {"name": "田中", "id": "42"}
        result = _resolve_runtime("${captured:name} (ID: ${captured:id})", vars_)
        assert result == "田中 (ID: 42)"

    def test_unknown_var_unchanged(self):
        assert _resolve_runtime("${captured:unknown}", {}) == "${captured:unknown}"

    def test_no_captured_pattern(self):
        assert _resolve_runtime("plain text", {"x": "y"}) == "plain text"

    def test_empty_string(self):
        assert _resolve_runtime("", {"x": "y"}) == ""

    def test_none_input(self):
        assert _resolve_runtime(None, {"x": "y"}) is None

    def test_mixed_with_other_vars(self):
        """${captured:xxx} 以外の ${xxx} パターンはそのまま."""
        vars_ = {"val": "OK"}
        result = _resolve_runtime("${base_url}/${captured:val}", vars_)
        assert result == "${base_url}/OK"


class TestParseRetryFromNote:
    """備考欄の retry:N / retry_wait:N 解析テスト."""

    def test_no_retry(self):
        assert _parse_retry_from_note("") == (0, 1000)
        assert _parse_retry_from_note(None) == (0, 1000)
        assert _parse_retry_from_note("通常の備考") == (0, 1000)

    def test_retry_only(self):
        assert _parse_retry_from_note("retry:3") == (3, 1000)

    def test_retry_and_wait(self):
        assert _parse_retry_from_note("retry:5 retry_wait:2000") == (5, 2000)

    def test_retry_with_other_text(self):
        count, wait = _parse_retry_from_note("ネットワーク不安定 retry:2 retry_wait:500")
        assert count == 2
        assert wait == 500

    def test_invalid_retry_value(self):
        assert _parse_retry_from_note("retry:abc") == (0, 1000)


class TestVerifyDownload:
    """ダウンロードファイル検証テスト."""

    def test_file_not_found(self):
        step = TestStep(row=1, no=1, item="", action="", selector="",
                        input_val="", verify_type="download",
                        verify_target="missing.csv", expected="", note="")
        passed, msg = verify_download(None, step)
        assert passed is False

    def test_file_exists_no_expected(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            f.write("a,b\n1,2\n")
            path = Path(f.name)
        step = TestStep(row=1, no=1, item="", action="", selector="",
                        input_val="", verify_type="download",
                        verify_target="test.csv", expected="", note="")
        passed, msg = verify_download(path, step)
        assert passed is True
        path.unlink()

    def test_file_contains(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            f.write("name,age\n田中太郎,30\n")
            path = Path(f.name)
        step = TestStep(row=1, no=1, item="", action="", selector="",
                        input_val="", verify_type="download",
                        verify_target="test.csv", expected="contains:田中太郎",
                        note="")
        passed, msg = verify_download(path, step)
        assert passed is True
        path.unlink()

    def test_file_not_contains(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            f.write("name\n鈴木\n")
            path = Path(f.name)
        step = TestStep(row=1, no=1, item="", action="", selector="",
                        input_val="", verify_type="download",
                        verify_target="test.csv", expected="contains:田中",
                        note="")
        passed, msg = verify_download(path, step)
        assert passed is False
        path.unlink()
