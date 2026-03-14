"""Config - YAML設定の読み込みと管理"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG = {
    "output_dir": "./output",
    "catalog_path": "./output/catalog.jsonl",
    "agents": {},
}


def load_config(path: str | Path) -> dict[str, Any]:
    """YAML設定ファイルを読み込む。存在しなければデフォルトを返す。"""
    path = Path(path)
    if not path.exists():
        return dict(DEFAULT_CONFIG)
    with open(path, encoding="utf-8") as f:
        user_config = yaml.safe_load(f) or {}
    config = dict(DEFAULT_CONFIG)
    config.update(user_config)
    return config


def get_agent_config(config: dict[str, Any], agent_name: str) -> dict[str, Any]:
    """指定エージェントの設定を取得する。"""
    agents = config.get("agents", {})
    return agents.get(agent_name, {})
