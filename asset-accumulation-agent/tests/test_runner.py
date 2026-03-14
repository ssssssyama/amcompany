"""Runnerのテスト"""

from pathlib import Path
from typing import Any

from src.agent import Asset, BaseAgent, Context
from src.catalog import Catalog
from src.runner import run_agent_cycle


class DummyAgent(BaseAgent):
    name = "dummy"
    description = "テスト用ダミーエージェント"
    interval_seconds = 60
    monetization = "direct_sale"

    def __init__(self, assets_to_generate: int = 3, should_fail: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.assets_to_generate = assets_to_generate
        self.should_fail = should_fail

    def run(self, ctx: Context) -> list[Asset]:
        if self.should_fail:
            raise RuntimeError("テストエラー")

        assets = []
        for i in range(self.assets_to_generate):
            # テスト用テキストファイルを作成
            path = ctx.output_dir / f"dummy_{i}.txt"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"Dummy content {i}" * 20)  # 品質通過するように長めに
            assets.append(Asset(
                id=f"dummy_{i:03d}",
                agent=self.name,
                type="text/plain",
                path=str(path),
                monetization="direct_sale",
                estimated_value_yen=10.0,
            ))
        return assets

    def estimate_value(self, catalog: Any) -> float:
        return self.assets_to_generate * 10.0


class TestRunAgentCycle:
    def test_successful_cycle(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")
        agent = DummyAgent(assets_to_generate=3)
        ctx = Context(output_dir=tmp_path / "output", config={}, catalog=catalog)

        passed = run_agent_cycle(agent, ctx, catalog)
        assert passed == 3
        assert len(catalog.all_assets) == 3

    def test_failed_cycle(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")
        agent = DummyAgent(should_fail=True)
        ctx = Context(output_dir=tmp_path / "output", config={}, catalog=catalog)

        passed = run_agent_cycle(agent, ctx, catalog)
        assert passed == 0
        assert len(catalog.all_assets) == 0

    def test_quality_filtering(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")
        agent = DummyAgent(assets_to_generate=2)
        ctx = Context(output_dir=tmp_path / "output", config={}, catalog=catalog)

        passed = run_agent_cycle(agent, ctx, catalog, quality_threshold=0.7)
        # テキストファイルは十分な長さがあるので全て通過するはず
        assert passed == 2

    def test_marks_run_time(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")
        agent = DummyAgent()
        ctx = Context(output_dir=tmp_path / "output", config={}, catalog=catalog)

        assert agent.should_run(catalog)
        run_agent_cycle(agent, ctx, catalog)
        # 実行直後は should_run が False（interval未経過）
        assert not agent.should_run(catalog)
