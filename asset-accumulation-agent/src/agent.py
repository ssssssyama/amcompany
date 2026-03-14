"""BaseAgent - 資産蓄積エージェントの基底クラス"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Asset:
    """生成されたアセット1件"""

    id: str
    agent: str
    type: str  # "audio/wav", "image/png", "text/markdown" etc.
    path: str
    monetization: str  # "direct_sale", "traffic", "indirect"
    estimated_value_yen: float = 0.0
    status: str = "generated"  # generated -> quality_passed -> packaged -> listed -> sold
    quality_score: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "type": self.type,
            "path": self.path,
            "monetization": self.monetization,
            "estimated_value_yen": self.estimated_value_yen,
            "status": self.status,
            "quality_score": self.quality_score,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Asset:
        return cls(**d)


@dataclass
class Context:
    """エージェント実行時のコンテキスト"""

    output_dir: Path
    config: dict[str, Any]
    catalog: Any  # Catalog instance (avoid circular import)
    cycle: int = 0


class BaseAgent(ABC):
    """資産蓄積エージェントの基底クラス

    サブクラスは run() と estimate_value() を実装する。
    1サイクルの run() で1つ以上の Asset を生成して返す。
    """

    name: str = ""
    description: str = ""
    interval_seconds: int = 3600
    requires: list[str] = []  # "gpu", "network", "api_key"
    monetization: str = "direct_sale"  # "direct_sale", "traffic", "indirect"

    def __init__(self, params: dict[str, Any] | None = None):
        self.params = params or {}
        self._last_run: float = 0.0

    @abstractmethod
    def run(self, ctx: Context) -> list[Asset]:
        """1サイクル実行。生成したAssetのリストを返す。"""

    @abstractmethod
    def estimate_value(self, catalog: Any) -> float:
        """次の生成サイクルの推定価値（円）を返す。

        カタログの現状を見て、何を生成すべきかを判断し、
        その推定収益を返す。Runnerはこれで優先順位を決める。
        """

    def should_run(self, catalog: Any) -> bool:
        """実行すべきかどうかを判定する。"""
        elapsed = time.time() - self._last_run
        return elapsed >= self.interval_seconds

    def mark_run(self) -> None:
        """実行完了を記録する。"""
        self._last_run = time.time()
