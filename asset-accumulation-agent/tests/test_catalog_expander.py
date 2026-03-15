"""CatalogExpanderAgentのテスト"""

from pathlib import Path

from src.agent import Context
from src.catalog import Catalog
from src.agents.catalog_expander import (
    CatalogExpanderAgent,
    FRAME_THEMES,
    FORTUNE_THEMES,
    FOOTSTEP_EXPANSION_THEMES,
)


class TestCatalogExpanderAgent:
    def _make_ctx(self, tmp_path: Path) -> tuple[Context, Catalog]:
        catalog = Catalog(tmp_path / "catalog.jsonl")
        ctx = Context(
            output_dir=tmp_path / "output", config={}, catalog=catalog
        )
        return ctx, catalog

    def test_generates_frame_packs(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        agent = CatalogExpanderAgent(params={"max_per_cycle": 2})

        assets = agent.run(ctx)
        assert len(assets) == 2
        assert assets[0].metadata["product_type"] == "frame_pack"
        # ファイルが実際に生成されている
        assert Path(assets[0].path).exists()

    def test_generates_fortune_packs(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        # max_per_cycleをフレーム数と同じにして、1回目はフレームのみ生成
        frame_count = len(FRAME_THEMES)
        agent = CatalogExpanderAgent(
            params={"max_per_cycle": frame_count}
        )
        # 1回目でフレームパックを全生成
        assets1 = agent.run(ctx)
        assert len(assets1) == frame_count
        catalog.add_many(assets1)

        # 2回目ではフレーム済み → おみくじパックが来る
        assets2 = agent.run(ctx)
        fortune_assets = [
            a for a in assets2 if a.metadata.get("product_type") == "fortune_pack"
        ]
        assert len(fortune_assets) > 0
        # fortune_data.json が存在する
        for a in fortune_assets:
            assert Path(a.path).exists()
            import json
            data = json.loads(Path(a.path).read_text())
            assert "fortunes" in data
            assert "lucky_items" in data

    def test_generates_footstep_prompts(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        agent = CatalogExpanderAgent(
            params={"max_per_cycle": 50}
        )
        assets = agent.run(ctx)
        catalog.add_many(assets)

        footstep_assets = [
            a for a in assets if a.metadata.get("product_type") == "footstep_prompts"
        ]
        assert len(footstep_assets) == len(FOOTSTEP_EXPANSION_THEMES)

    def test_no_duplicates(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        agent = CatalogExpanderAgent(params={"max_per_cycle": 50})

        # 1回目
        assets1 = agent.run(ctx)
        catalog.add_many(assets1)
        for a in assets1:
            catalog.update_status(a.id, "quality_passed")
        count1 = len(assets1)

        # 2回目 — 全て生成済みなので0件
        assets2 = agent.run(ctx)
        assert len(assets2) == 0

        # 合計数チェック
        total_expected = (
            len(FRAME_THEMES)
            + len(FORTUNE_THEMES)
            + len(FOOTSTEP_EXPANSION_THEMES)
        )
        assert count1 == total_expected

    def test_estimate_value_decreases(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        agent = CatalogExpanderAgent(params={"max_per_cycle": 50})

        # 初期: 全て未生成なので高い値
        value_before = agent.estimate_value(catalog)
        assert value_before > 0

        # 全生成後
        assets = agent.run(ctx)
        catalog.add_many(assets)
        value_after = agent.estimate_value(catalog)
        assert value_after == 0

    def test_frame_pack_files_structure(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        agent = CatalogExpanderAgent(params={"max_per_cycle": 1})

        assets = agent.run(ctx)
        assert len(assets) == 1
        asset = assets[0]

        pack_dir = Path(asset.path).parent
        assert (pack_dir / "frames.json").exists()
        assert (pack_dir / "preview.txt").exists()
        assert (pack_dir / "README.txt").exists()
