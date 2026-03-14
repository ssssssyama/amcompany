"""Catalog - 生成アセットの台帳管理（JSON Lines形式）"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent import Asset


class Catalog:
    """アセットカタログ。JSON Lines形式で追記管理。

    追記のみの設計により、ロック不要で並行書き込みに強い。
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._assets: list[Asset] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._assets = []
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._assets.append(Asset.from_dict(json.loads(line)))
        self._loaded = True

    def add(self, asset: Asset) -> None:
        """アセットをカタログに追加（ファイルに追記）"""
        self._ensure_loaded()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asset.to_dict(), ensure_ascii=False) + "\n")
        self._assets.append(asset)

    def add_many(self, assets: list[Asset]) -> None:
        """複数アセットを一括追加"""
        for asset in assets:
            self.add(asset)

    def query(
        self,
        agent: str | None = None,
        asset_type: str | None = None,
        status: str | None = None,
        since: str | None = None,
    ) -> list[Asset]:
        """条件でフィルタしてアセットを検索"""
        self._ensure_loaded()
        results = self._assets
        if agent:
            results = [a for a in results if a.agent == agent]
        if asset_type:
            results = [a for a in results if a.type == asset_type]
        if status:
            results = [a for a in results if a.status == status]
        if since:
            results = [a for a in results if a.created_at >= since]
        return results

    def count(self, agent: str | None = None, **metadata_filters: Any) -> int:
        """条件に一致するアセット数を返す"""
        self._ensure_loaded()
        results = self._assets
        if agent:
            results = [a for a in results if a.agent == agent]
        for key, value in metadata_filters.items():
            results = [a for a in results if a.metadata.get(key) == value]
        return len(results)

    def stats(self) -> dict[str, Any]:
        """蓄積状況のサマリーを返す"""
        self._ensure_loaded()
        by_agent: dict[str, dict[str, Any]] = {}
        by_status: dict[str, int] = {}
        total_value = 0.0

        for asset in self._assets:
            # エージェント別
            if asset.agent not in by_agent:
                by_agent[asset.agent] = {"count": 0, "total_value_yen": 0.0}
            by_agent[asset.agent]["count"] += 1
            by_agent[asset.agent]["total_value_yen"] += asset.estimated_value_yen

            # ステータス別
            by_status[asset.status] = by_status.get(asset.status, 0) + 1

            total_value += asset.estimated_value_yen

        return {
            "total_assets": len(self._assets),
            "total_estimated_value_yen": total_value,
            "by_agent": by_agent,
            "by_status": by_status,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def update_status(self, asset_id: str, new_status: str) -> bool:
        """アセットのステータスを更新する。

        JSON Linesは追記のみのため、更新行を末尾に追加する。
        読み込み時は同一IDの最新行が有効。
        """
        self._ensure_loaded()
        for asset in reversed(self._assets):
            if asset.id == asset_id:
                asset.status = new_status
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(asset.to_dict(), ensure_ascii=False) + "\n")
                return True
        return False

    @property
    def all_assets(self) -> list[Asset]:
        """全アセットを返す（重複IDは最新のみ）"""
        self._ensure_loaded()
        seen: dict[str, Asset] = {}
        for asset in self._assets:
            seen[asset.id] = asset
        return list(seen.values())
