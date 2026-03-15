"""PackagerAgentのテスト"""

import json
import zipfile
from pathlib import Path

from src.agent import Asset, Context
from src.catalog import Catalog
from src.agents.catalog_expander import CatalogExpanderAgent
from src.agents.packager import PackagerAgent
from src.quality import run_quality_check


class TestPackagerAgent:
    def _make_ctx(self, tmp_path: Path) -> tuple[Context, Catalog]:
        catalog = Catalog(tmp_path / "catalog.jsonl")
        ctx = Context(
            output_dir=tmp_path / "output", config={}, catalog=catalog
        )
        return ctx, catalog

    def _seed_catalog(self, ctx: Context, catalog: Catalog) -> list[Asset]:
        """catalog_expanderで素材を生成し、品質通過させる。"""
        expander = CatalogExpanderAgent(params={"max_per_cycle": 3})
        assets = expander.run(ctx)
        for asset in assets:
            ok, score = run_quality_check(asset, threshold=0.3)
            asset.quality_score = score
            if ok:
                asset.status = "quality_passed"
            catalog.add(asset)
        return assets

    def test_packages_quality_passed_assets(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        self._seed_catalog(ctx, catalog)

        packager = PackagerAgent(params={"max_per_cycle": 3})
        packages = packager.run(ctx)

        assert len(packages) > 0
        for pkg in packages:
            assert pkg.type == "application/zip"
            assert Path(pkg.path).exists()

    def test_zip_contains_files(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        self._seed_catalog(ctx, catalog)

        packager = PackagerAgent(params={"max_per_cycle": 1})
        packages = packager.run(ctx)
        assert len(packages) >= 1

        zip_path = Path(packages[0].path)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            # ZIPにファイルが含まれている
            assert len(names) > 0

    def test_listing_files_generated(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        self._seed_catalog(ctx, catalog)

        packager = PackagerAgent(params={"max_per_cycle": 1})
        packages = packager.run(ctx)
        assert len(packages) >= 1

        pkg_dir = Path(packages[0].path).parent
        assert (pkg_dir / "listing_ja.md").exists()
        assert (pkg_dir / "listing_en.md").exists()
        assert (pkg_dir / "metadata.json").exists()

    def test_cross_references_generated(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        # 複数のアセットを生成して相互参照が生まれるようにする
        expander = CatalogExpanderAgent(params={"max_per_cycle": 10})
        assets = expander.run(ctx)
        for asset in assets:
            asset.status = "quality_passed"
            catalog.add(asset)

        packager = PackagerAgent(params={"max_per_cycle": 10})
        packages = packager.run(ctx)

        # 少なくとも1つのパッケージにクロスリファレンスがある
        has_cross_refs = False
        for pkg in packages:
            pkg_dir = Path(pkg.path).parent
            cross_ref_path = pkg_dir / "cross_references.json"
            if cross_ref_path.exists():
                refs = json.loads(cross_ref_path.read_text())
                if len(refs) > 0:
                    has_cross_refs = True
                    break
        assert has_cross_refs

    def test_no_duplicate_packaging(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        self._seed_catalog(ctx, catalog)

        packager = PackagerAgent(params={"max_per_cycle": 10})

        # 1回目
        packages1 = packager.run(ctx)
        for pkg in packages1:
            catalog.add(pkg)
        count1 = len(packages1)
        assert count1 > 0

        # 2回目 — 同じアセットは再パッケージされない
        packages2 = packager.run(ctx)
        assert len(packages2) == 0

    def test_estimate_value(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        self._seed_catalog(ctx, catalog)

        packager = PackagerAgent()
        value = packager.estimate_value(catalog)
        assert value > 0

    def test_metadata_contains_price(self, tmp_path: Path):
        ctx, catalog = self._make_ctx(tmp_path)
        self._seed_catalog(ctx, catalog)

        packager = PackagerAgent(params={"max_per_cycle": 1})
        packages = packager.run(ctx)
        assert len(packages) >= 1

        pkg = packages[0]
        assert "price_yen" in pkg.metadata
        assert pkg.metadata["price_yen"] > 0
