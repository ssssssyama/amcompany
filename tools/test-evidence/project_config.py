"""プロジェクト設定ファイルの読み込みモジュール.

YAMLファイルからプロジェクト固有の設定（環境情報・認証・ブラウザ設定等）を読み込む。
Excelテスト仕様書内の変数（${変数名}）を設定値で置換する機能を提供する。
"""

import re
from pathlib import Path

import yaml


class ProjectConfig:
    """プロジェクト設定を管理するクラス."""

    def __init__(self, config_path: str | None = None):
        self.raw: dict = {}
        if config_path:
            self.raw = self._load(config_path)

    def _load(self, config_path: str) -> dict:
        """YAML設定ファイルを読み込む."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data

    # --- 環境設定 ---

    @property
    def base_url(self) -> str:
        """テスト対象アプリのベースURL."""
        return self.raw.get("environment", {}).get("base_url", "")

    @property
    def variables(self) -> dict[str, str]:
        """テスト仕様書内で使える変数 (${変数名} で参照)."""
        return self.raw.get("environment", {}).get("variables", {})

    # --- 認証設定 ---

    @property
    def auth(self) -> dict:
        """認証設定."""
        return self.raw.get("auth", {})

    @property
    def auth_type(self) -> str:
        """認証方式 (none / basic / form / cookie)."""
        return self.auth.get("type", "none")

    # --- ブラウザ設定 ---

    @property
    def viewport(self) -> dict:
        """ブラウザのビューポートサイズ."""
        default = {"width": 1280, "height": 720}
        return self.raw.get("browser", {}).get("viewport", default)

    @property
    def locale(self) -> str:
        """ブラウザのロケール."""
        return self.raw.get("browser", {}).get("locale", "ja-JP")

    @property
    def timeout(self) -> int:
        """操作のデフォルトタイムアウト（ミリ秒）."""
        return self.raw.get("browser", {}).get("timeout", 30000)

    @property
    def ignore_https_errors(self) -> bool:
        """HTTPS証明書エラーを無視するか."""
        return self.raw.get("browser", {}).get("ignore_https_errors", False)

    # --- A5M2設定 ---

    @property
    def a5m2_cmd(self) -> str | None:
        """A5M2cmd.exe のパス."""
        return self.raw.get("a5m2", {}).get("cmd")

    @property
    def a5m2_connect(self) -> str | None:
        """A5M2の接続文字列."""
        return self.raw.get("a5m2", {}).get("connect")

    # --- 変数置換 ---

    def resolve(self, text: str) -> str:
        """テキスト内の ${変数名} をプロジェクト設定の値で置換する.

        置換対象:
        - ${base_url} → environment.base_url
        - ${変数名}   → environment.variables.変数名
        """
        if not text or "${" not in text:
            return text

        variables = {"base_url": self.base_url, **self.variables}

        def replacer(match):
            key = match.group(1)
            return variables.get(key, match.group(0))

        return re.sub(r"\$\{(\w+)\}", replacer, text)
