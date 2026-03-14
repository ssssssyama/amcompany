"""Catalogのテスト"""

import json
import tempfile
from pathlib import Path

from src.agent import Asset
from src.catalog import Catalog


def _make_asset(id: str = "test_001", agent: str = "test_agent", **kwargs) -> Asset:
    defaults = {
        "type": "audio/wav",
        "path": "/tmp/test.wav",
        "monetization": "direct_sale",
        "estimated_value_yen": 10.0,
        "status": "generated",
        "metadata": {},
    }
    defaults.update(kwargs)
    return Asset(id=id, agent=agent, **defaults)


class TestCatalog:
    def test_add_and_query(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")
        asset = _make_asset()
        catalog.add(asset)

        results = catalog.query(agent="test_agent")
        assert len(results) == 1
        assert results[0].id == "test_001"

    def test_add_many(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")
        assets = [_make_asset(id=f"test_{i:03d}") for i in range(5)]
        catalog.add_many(assets)

        assert len(catalog.all_assets) == 5

    def test_query_filters(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")
        catalog.add(_make_asset(id="a1", agent="agent_a", status="generated"))
        catalog.add(_make_asset(id="a2", agent="agent_a", status="quality_passed"))
        catalog.add(_make_asset(id="b1", agent="agent_b", status="generated"))

        assert len(catalog.query(agent="agent_a")) == 2
        assert len(catalog.query(status="quality_passed")) == 1
        assert len(catalog.query(agent="agent_b")) == 1

    def test_count_with_metadata(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")
        catalog.add(_make_asset(id="a1", metadata={"theme": "horror", "surface": "wood"}))
        catalog.add(_make_asset(id="a2", metadata={"theme": "horror", "surface": "stone"}))
        catalog.add(_make_asset(id="a3", metadata={"theme": "scifi", "surface": "wood"}))

        assert catalog.count(agent="test_agent", theme="horror") == 2
        assert catalog.count(agent="test_agent", surface="wood") == 2
        assert catalog.count(agent="test_agent", theme="horror", surface="wood") == 1

    def test_stats(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")
        catalog.add(_make_asset(id="a1", agent="audio", estimated_value_yen=10.0))
        catalog.add(_make_asset(id="a2", agent="audio", estimated_value_yen=10.0))
        catalog.add(_make_asset(id="b1", agent="image", estimated_value_yen=5.0))

        stats = catalog.stats()
        assert stats["total_assets"] == 3
        assert stats["total_estimated_value_yen"] == 25.0
        assert stats["by_agent"]["audio"]["count"] == 2
        assert stats["by_agent"]["image"]["count"] == 1

    def test_update_status(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")
        catalog.add(_make_asset(id="a1", status="generated"))

        assert catalog.update_status("a1", "quality_passed")
        assets = catalog.all_assets
        assert len(assets) == 1
        assert assets[0].status == "quality_passed"

    def test_persistence(self, tmp_path: Path):
        path = tmp_path / "catalog.jsonl"

        # 書き込み
        cat1 = Catalog(path)
        cat1.add(_make_asset(id="a1"))
        cat1.add(_make_asset(id="a2"))

        # 別インスタンスで読み込み
        cat2 = Catalog(path)
        assert len(cat2.all_assets) == 2

    def test_empty_catalog(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")
        assert len(catalog.all_assets) == 0
        assert catalog.stats()["total_assets"] == 0
        assert catalog.count() == 0
