"""ImageVariantsAgent - 画像バリエーション生成エージェント

ベース画像からアップスケール・スタイル変換でバリエーションを生成し、
テクスチャパック等として販売可能な在庫を積み上げる。
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from ..agent import Asset, BaseAgent, Context

logger = logging.getLogger(__name__)

STYLES = {
    "anime": {"model": "x4plus-anime", "description": "アニメ調"},
    "realistic": {"model": "x4plus", "description": "リアル調"},
}


class ImageVariantsAgent(BaseAgent):
    name = "image_variants"
    description = "画像バリエーション生成（アップスケール・スタイル変換）"
    interval_seconds = 1800
    requires = ["gpu"]
    monetization = "direct_sale"

    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        self.source_dir = Path(self.params.get("source_dir", "./assets/base_images"))
        self.styles = self.params.get("styles", list(STYLES.keys()))
        self.scale = self.params.get("scale", 4)
        self.max_per_cycle = self.params.get("max_per_cycle", 20)

    def _find_source_images(self) -> list[Path]:
        """ソースディレクトリから画像ファイルを検出する。"""
        if not self.source_dir.exists():
            return []
        extensions = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tiff", ".webp"}
        return [
            p for p in self.source_dir.rglob("*")
            if p.suffix.lower() in extensions
        ]

    def _upscale_image(self, input_path: Path, output_path: Path, style: str) -> bool:
        """画像をアップスケールする。"""
        try:
            from PIL import Image

            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Real-ESRGANが使える場合
            try:
                from realesrgan import RealESRGANer
                from basicsr.archs.rrdbnet_arch import RRDBNet
                import torch

                model_name = STYLES.get(style, {}).get("model", "x4plus-anime")
                model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=6, num_grow_ch=32, scale=4)
                device = "cuda" if torch.cuda.is_available() else "cpu"

                upsampler = RealESRGANer(
                    scale=self.scale,
                    model_path=None,  # auto-download
                    model=model,
                    device=device,
                )
                import cv2
                import numpy as np

                img = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
                output, _ = upsampler.enhance(img, outscale=self.scale)
                cv2.imwrite(str(output_path), output)
                return True

            except ImportError:
                # Real-ESRGANなし: PILでシンプルリサイズ（デモモード）
                with Image.open(input_path) as img:
                    new_size = (img.width * self.scale, img.height * self.scale)
                    upscaled = img.resize(new_size, Image.LANCZOS)
                    upscaled.save(output_path)
                return True

        except ImportError:
            logger.warning("Pillowが未インストール。デモスキップします。")
            return False
        except Exception as e:
            logger.error(f"画像処理失敗: {e}")
            return False

    def run(self, ctx: Context) -> list[Asset]:
        sources = self._find_source_images()
        if not sources:
            logger.info(f"[image_variants] ソース画像なし ({self.source_dir})")
            return []

        assets: list[Asset] = []
        count = 0

        for source in sources:
            if count >= self.max_per_cycle:
                break

            for style in self.styles:
                if count >= self.max_per_cycle:
                    break

                # 既に生成済みかチェック
                asset_id = f"img_{source.stem}_{style}"
                existing = ctx.catalog.count(agent=self.name, source=source.stem, style=style)
                if existing > 0:
                    continue

                output_path = (
                    ctx.output_dir / "textures" / style / f"{source.stem}_x{self.scale}{source.suffix}"
                )

                if self._upscale_image(source, output_path, style):
                    asset = Asset(
                        id=asset_id,
                        agent=self.name,
                        type=f"image/{source.suffix.lstrip('.')}",
                        path=str(output_path),
                        monetization="direct_sale",
                        estimated_value_yen=10.0,
                        metadata={
                            "source": source.stem,
                            "style": style,
                            "scale": self.scale,
                            "original_path": str(source),
                        },
                    )
                    assets.append(asset)
                    count += 1

        return assets

    def estimate_value(self, catalog: Any) -> float:
        sources = self._find_source_images()
        total_possible = len(sources) * len(self.styles)
        existing = catalog.count(agent=self.name)
        remaining = max(0, total_possible - existing)
        return remaining * 10.0  # ¥10/枚
