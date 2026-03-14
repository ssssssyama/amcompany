"""AudioPackAgent - テーマ別音源パック生成エージェント

Stable Audio Openを使ってテーマ別の足音バリエーションを大量生成。
各テーマ x サーフェスの組み合わせでパックを構成し、BOOTH等で販売可能な在庫を積み上げる。
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from pathlib import Path
from typing import Any

from ..agent import Asset, BaseAgent, Context

logger = logging.getLogger(__name__)

THEMES = {
    "horror": {"prefix": "creepy", "mood": "dark, horror, eerie, haunted"},
    "scifi": {"prefix": "futuristic", "mood": "sci-fi, spaceship, metallic, electronic"},
    "fantasy": {"prefix": "medieval", "mood": "fantasy, dungeon, castle, mystical"},
    "nature": {"prefix": "natural", "mood": "outdoor, peaceful, forest, ambient"},
    "urban": {"prefix": "city", "mood": "urban, street, concrete, busy"},
}

SURFACES = {
    "wood": "wooden floor",
    "stone": "stone floor",
    "grass": "grass field",
    "metal": "metal grating",
    "gravel": "gravel path",
    "snow": "snow covered ground",
    "water": "shallow water puddle",
    "carpet": "thick carpet",
    "sand": "sandy beach",
    "tile": "ceramic tile floor",
}


def build_prompt(theme: str, surface: str) -> str:
    """テーマとサーフェスからAI生成プロンプトを構築する。"""
    theme_info = THEMES.get(theme, {"prefix": "", "mood": ""})
    surface_desc = SURFACES.get(surface, surface)
    return (
        f"single {theme_info['prefix']} footstep on {surface_desc}, "
        f"{theme_info['mood']}, short sound effect, mono"
    )


class AudioPackAgent(BaseAgent):
    name = "audio_pack"
    description = "テーマ別音源パック生成（Stable Audio Open）"
    interval_seconds = 3600
    requires = ["gpu"]
    monetization = "direct_sale"

    def __init__(self, params: dict[str, Any] | None = None):
        super().__init__(params)
        self._model = None
        self._model_config = None
        self.themes = self.params.get("themes", list(THEMES.keys()))
        self.surfaces = self.params.get("surfaces", list(SURFACES.keys()))
        self.variations_per_combo = self.params.get("variations_per_combo", 10)
        self.quality_threshold = self.params.get("quality_threshold", 0.7)

    def _load_model(self) -> bool:
        """Stable Audio Openモデルをロードする。"""
        if self._model is not None:
            return True
        try:
            import torch
            from stable_audio_tools import get_pretrained_model

            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model, self._model_config = get_pretrained_model(
                "stabilityai/stable-audio-open-1.0"
            )
            self._model = self._model.to(device)
            logger.info(f"モデルロード完了 (device={device})")
            return True
        except ImportError:
            logger.warning(
                "stable-audio-tools が未インストール。"
                "pip install stable-audio-tools torch torchaudio でインストールしてください。"
                "デモモードで動作します。"
            )
            return False
        except Exception as e:
            logger.error(f"モデルロード失敗: {e}")
            return False

    def _generate_audio(self, prompt: str, seed: int, output_path: Path) -> bool:
        """プロンプトから音声を生成する。"""
        if self._model is None:
            # デモモード: ダミーWAVを生成
            return self._generate_demo_audio(prompt, seed, output_path)

        try:
            import torch
            import torchaudio
            from stable_audio_tools.inference.generation import generate_diffusion_cond

            device = next(self._model.parameters()).device
            conditioning = [{"prompt": prompt, "seconds_total": 1.0}]

            generator = torch.Generator(device="cpu").manual_seed(seed)

            with torch.no_grad():
                output = generate_diffusion_cond(
                    self._model,
                    conditioning=conditioning,
                    sample_size=self._model_config["sample_size"],
                    sample_rate=self._model_config["sample_rate"],
                    device=device,
                    seed=seed,
                )

            audio = output[0].cpu()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            torchaudio.save(str(output_path), audio, self._model_config["sample_rate"])
            return True

        except Exception as e:
            logger.error(f"音声生成失敗: {e}")
            return False

    def _generate_demo_audio(self, prompt: str, seed: int, output_path: Path) -> bool:
        """デモ用: 短いサイン波WAVを生成する。"""
        import math
        import struct
        import wave

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 44100
        duration = 0.5
        frequency = 220 + (seed % 440)
        n_samples = int(sample_rate * duration)

        rng = random.Random(seed)
        samples = []
        for i in range(n_samples):
            t = i / sample_rate
            # 基本波 + ノイズでそれっぽく
            val = math.sin(2 * math.pi * frequency * t) * 0.3
            val += rng.uniform(-0.1, 0.1)
            # エンベロープ（急速に減衰）
            envelope = max(0, 1.0 - t * 4)
            val *= envelope
            samples.append(int(val * 32767))

        with wave.open(str(output_path), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))

        return True

    def _find_gaps(self, catalog: Any) -> list[tuple[str, str]]:
        """カタログを参照し、バリエーションが少ない組み合わせを見つける。"""
        gaps: list[tuple[str, str, int]] = []
        for theme in self.themes:
            for surface in self.surfaces:
                count = catalog.count(
                    agent=self.name, theme=theme, surface=surface
                )
                if count < self.variations_per_combo:
                    gaps.append((theme, surface, count))

        # 少ない順にソート
        gaps.sort(key=lambda x: x[2])
        return [(t, s) for t, s, _ in gaps]

    def run(self, ctx: Context) -> list[Asset]:
        has_model = self._load_model()
        mode = "AI生成" if has_model else "デモ"
        logger.info(f"[audio_pack] {mode}モードで実行")

        gaps = self._find_gaps(ctx.catalog)
        if not gaps:
            logger.info("[audio_pack] 全テーマ/サーフェスが目標数に到達済み")
            return []

        # 1サイクルで最大10件生成
        max_per_cycle = min(10, len(gaps))
        assets: list[Asset] = []

        for theme, surface in gaps[:max_per_cycle]:
            existing = ctx.catalog.count(
                agent=self.name, theme=theme, surface=surface
            )
            variation_num = existing + 1
            seed = int(hashlib.md5(
                f"{theme}_{surface}_{variation_num}_{time.time()}".encode()
            ).hexdigest()[:8], 16)

            prompt = build_prompt(theme, surface)
            filename = f"{surface}_{variation_num:03d}.wav"
            output_path = ctx.output_dir / "footsteps" / theme / filename

            if self._generate_audio(prompt, seed, output_path):
                asset = Asset(
                    id=f"audio_{theme}_{surface}_{variation_num:03d}",
                    agent=self.name,
                    type="audio/wav",
                    path=str(output_path),
                    monetization="direct_sale",
                    estimated_value_yen=self._estimate_single_value(theme, surface),
                    metadata={
                        "theme": theme,
                        "surface": surface,
                        "variation": variation_num,
                        "prompt": prompt,
                        "seed": seed,
                        "mode": mode,
                    },
                )
                assets.append(asset)

        return assets

    def _estimate_single_value(self, theme: str, surface: str) -> float:
        """1ファイルあたりの推定価値（円）"""
        # テーマパック300円 / 50ファイル = 6円/ファイル
        return 6.0

    def estimate_value(self, catalog: Any) -> float:
        gaps = self._find_gaps(catalog)
        # ギャップが多いほど価値が高い（売れるパックが増える）
        return len(gaps) * self._estimate_single_value("", "")
