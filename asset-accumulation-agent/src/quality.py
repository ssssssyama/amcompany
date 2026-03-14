"""Quality Gate - 売り物にならないアセットを弾くフィルタ"""

from __future__ import annotations

import struct
import wave
from pathlib import Path
from typing import Any

from .agent import Asset


def check_audio_quality(path: Path, threshold: float = 0.7) -> tuple[bool, float]:
    """音声ファイルの品質を判定する。

    Returns:
        (passed, score): 品質通過したかどうかとスコア(0.0-1.0)
    """
    if not path.exists():
        return False, 0.0

    try:
        with wave.open(str(path), "rb") as wf:
            n_frames = wf.getnframes()
            sample_width = wf.getsampwidth()
            n_channels = wf.getnchannels()

            if n_frames == 0:
                return False, 0.0

            frames = wf.readframes(n_frames)
            duration = n_frames / wf.getframerate()

            # 短すぎる音声は不可
            if duration < 0.1:
                return False, 0.1

            # RMSエネルギーを計算
            if sample_width == 2:
                fmt = f"<{n_frames * n_channels}h"
                samples = struct.unpack(fmt, frames)
                rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
                max_val = 32767.0
                normalized_rms = rms / max_val
            else:
                # 16bit以外はスコア0.5でパス扱い
                return True, 0.5

            # 無音に近い場合は不可
            if normalized_rms < 0.01:
                return False, 0.2

            # スコア計算（RMSが適度にある = 高スコア）
            score = min(1.0, normalized_rms * 10)
            return score >= threshold, score

    except Exception:
        return False, 0.0


def check_image_quality(path: Path, threshold: float = 0.7) -> tuple[bool, float]:
    """画像ファイルの品質を判定する。"""
    if not path.exists():
        return False, 0.0

    try:
        file_size = path.stat().st_size
        # 極端に小さいファイルは破損の可能性
        if file_size < 1024:
            return False, 0.1

        # PILが使える場合は解像度もチェック
        try:
            from PIL import Image

            with Image.open(path) as img:
                w, h = img.size
                if w < 64 or h < 64:
                    return False, 0.2
                score = min(1.0, (w * h) / (2048 * 2048))
                return score >= threshold, score
        except ImportError:
            # PILなしでもファイルサイズベースで判定
            score = min(1.0, file_size / (1024 * 1024))
            return score >= threshold, score

    except Exception:
        return False, 0.0


def check_text_quality(path: Path, threshold: float = 0.7) -> tuple[bool, float]:
    """テキストファイルの品質を判定する。"""
    if not path.exists():
        return False, 0.0

    try:
        content = path.read_text(encoding="utf-8")
        char_count = len(content)

        if char_count < 10:
            return False, 0.1

        # 文字数ベースのスコア（100文字以上で満点）
        score = min(1.0, char_count / 100)
        return score >= threshold, score

    except Exception:
        return False, 0.0


def run_quality_check(asset: Asset, threshold: float = 0.7) -> tuple[bool, float]:
    """アセットの種類に応じた品質チェックを実行する。"""
    path = Path(asset.path)

    if asset.type.startswith("audio/"):
        return check_audio_quality(path, threshold)
    elif asset.type.startswith("image/"):
        return check_image_quality(path, threshold)
    elif asset.type.startswith("text/"):
        return check_text_quality(path, threshold)
    else:
        # 未知のタイプはファイル存在チェックのみ
        return path.exists(), 0.5 if path.exists() else 0.0
