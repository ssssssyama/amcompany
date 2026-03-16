"""project_config.py のユニットテスト."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

# テスト対象モジュールのパスを追加
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from project_config import ProjectConfig


@pytest.fixture
def config_file(tmp_path):
    """テスト用設定ファイルを生成するフィクスチャ."""
    def _create(data: dict) -> str:
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
        return str(path)
    return _create


class TestResolve:
    """変数置換（resolve）のテスト."""

    def test_resolve_base_url(self, config_file):
        path = config_file({
            "environment": {"base_url": "http://localhost:5000"}
        })
        config = ProjectConfig(path)
        assert config.resolve("${base_url}/login") == "http://localhost:5000/login"

    def test_resolve_custom_variable(self, config_file):
        path = config_file({
            "environment": {
                "base_url": "http://example.com",
                "variables": {"test_user": "tanaka", "test_pass": "secret"},
            }
        })
        config = ProjectConfig(path)
        assert config.resolve("${test_user}") == "tanaka"
        assert config.resolve("${test_pass}") == "secret"

    def test_resolve_unknown_variable_unchanged(self, config_file):
        path = config_file({"environment": {"base_url": "http://x"}})
        config = ProjectConfig(path)
        assert config.resolve("${unknown}") == "${unknown}"

    def test_resolve_empty_string(self, config_file):
        path = config_file({})
        config = ProjectConfig(path)
        assert config.resolve("") == ""
        assert config.resolve(None) is None

    def test_resolve_no_variables(self, config_file):
        path = config_file({})
        config = ProjectConfig(path)
        assert config.resolve("plain text") == "plain text"

    def test_resolve_env_variable(self, config_file, monkeypatch):
        """${env:VAR} でOS環境変数を参照できること."""
        monkeypatch.setenv("MY_SECRET_PASS", "s3cret!")
        path = config_file({})
        config = ProjectConfig(path)
        assert config.resolve("${env:MY_SECRET_PASS}") == "s3cret!"

    def test_resolve_env_variable_missing_raises(self, config_file, monkeypatch):
        """未設定の環境変数を参照するとValueErrorが発生すること."""
        monkeypatch.delenv("NONEXISTENT_VAR_12345", raising=False)
        path = config_file({})
        config = ProjectConfig(path)
        with pytest.raises(ValueError, match="環境変数.*NONEXISTENT_VAR_12345"):
            config.resolve("${env:NONEXISTENT_VAR_12345}")

    def test_resolve_env_mixed_with_config_vars(self, config_file, monkeypatch):
        """環境変数と設定変数を同一文字列内で混在使用できること."""
        monkeypatch.setenv("DB_HOST", "192.168.1.100")
        path = config_file({
            "environment": {
                "base_url": "http://localhost",
                "variables": {"db_port": "5432"},
            }
        })
        config = ProjectConfig(path)
        result = config.resolve("${env:DB_HOST}:${db_port}")
        assert result == "192.168.1.100:5432"


class TestProperties:
    """各プロパティのデフォルト値テスト."""

    def test_defaults_without_config(self):
        config = ProjectConfig()
        assert config.base_url == ""
        assert config.variables == {}
        assert config.auth_type == "none"
        assert config.viewport == {"width": 1280, "height": 720}
        assert config.locale == "ja-JP"
        assert config.timeout == 30000
        assert config.on_fail == "continue"
        assert config.excel_data_start_row == 7
        assert config.setup_sql is None
        assert config.teardown_sql is None
        assert config.output_dir is None
        assert config.output_timestamp is False

    def test_custom_values(self, config_file):
        path = config_file({
            "environment": {"base_url": "http://test.local"},
            "browser": {"timeout": 5000, "locale": "en-US"},
            "test": {"on_fail": "abort"},
            "db": {
                "type": "sqlite", "path": "test.db",
                "setup_sql": "DELETE FROM t;",
                "teardown_sql": "DROP TABLE t;",
            },
            "output": {"dir": "out", "timestamp": True},
        })
        config = ProjectConfig(path)
        assert config.base_url == "http://test.local"
        assert config.timeout == 5000
        assert config.locale == "en-US"
        assert config.on_fail == "abort"
        assert config.db_type == "sqlite"
        assert config.sqlite_path == "test.db"
        assert config.setup_sql == "DELETE FROM t;"
        assert config.teardown_sql == "DROP TABLE t;"
        assert config.output_dir == "out"
        assert config.output_timestamp is True

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            ProjectConfig("/nonexistent/config.yaml")
