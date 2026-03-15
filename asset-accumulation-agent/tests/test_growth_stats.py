"""カタログ成長分析のテスト"""

from pathlib import Path

from src.agent import Asset
from src.catalog import Catalog


class TestGrowthStats:
    def test_empty_catalog(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")
        growth = catalog.growth_stats()
        assert growth["total_products"] == 0
        assert growth["cross_reference_density"] == 0
        assert growth["estimated_exposure"] == 0

    def test_with_products(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")

        for i in range(5):
            asset = Asset(
                id=f"test_{i}",
                agent="catalog_expander",
                type="text/json",
                path=f"/tmp/test_{i}.json",
                monetization="direct_sale",
                estimated_value_yen=100.0,
                metadata={
                    "product_type": "frame_pack",
                    "theme": f"theme_{i}",
                    "tags_ja": ["VRChat", "Chatbox"],
                    "cross_ref_count": 2,
                },
            )
            catalog.add(asset)

        growth = catalog.growth_stats()
        assert growth["total_products"] == 5
        assert growth["by_product_type"]["frame_pack"] == 5
        assert growth["cross_reference_density"] == 2.0
        assert growth["estimated_exposure"] > 0
        assert growth["total_estimated_value_yen"] == 500.0

    def test_mixed_product_types(self, tmp_path: Path):
        catalog = Catalog(tmp_path / "catalog.jsonl")

        catalog.add(Asset(
            id="frame_1", agent="catalog_expander", type="text/json",
            path="/tmp/f.json", monetization="direct_sale",
            metadata={"product_type": "frame_pack"},
        ))
        catalog.add(Asset(
            id="fortune_1", agent="catalog_expander", type="text/json",
            path="/tmp/fo.json", monetization="direct_sale",
            metadata={"product_type": "fortune_pack"},
        ))
        catalog.add(Asset(
            id="audio_1", agent="audio_pack", type="audio/wav",
            path="/tmp/a.wav", monetization="direct_sale",
            metadata={"product_type": "audio_pack"},
        ))

        growth = catalog.growth_stats()
        assert growth["total_products"] == 3
        assert growth["by_product_type"]["frame_pack"] == 1
        assert growth["by_product_type"]["fortune_pack"] == 1
        assert growth["by_product_type"]["audio_pack"] == 1
