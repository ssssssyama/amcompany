"""品質ゲートのテスト"""

import math
import struct
import wave
from pathlib import Path

from src.agent import Asset
from src.quality import check_audio_quality, check_text_quality, run_quality_check


def _create_wav(path: Path, duration: float = 0.5, amplitude: float = 0.3) -> None:
    """テスト用WAVファイルを生成する。"""
    sample_rate = 44100
    n_samples = int(sample_rate * duration)
    samples = []
    for i in range(n_samples):
        t = i / sample_rate
        val = math.sin(2 * math.pi * 440 * t) * amplitude
        samples.append(int(val * 32767))

    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))


class TestAudioQuality:
    def test_good_audio(self, tmp_path: Path):
        wav_path = tmp_path / "good.wav"
        _create_wav(wav_path, duration=0.5, amplitude=0.3)
        passed, score = check_audio_quality(wav_path)
        assert passed
        assert score > 0.7

    def test_silent_audio(self, tmp_path: Path):
        wav_path = tmp_path / "silent.wav"
        _create_wav(wav_path, duration=0.5, amplitude=0.0001)
        passed, score = check_audio_quality(wav_path)
        assert not passed

    def test_too_short_audio(self, tmp_path: Path):
        wav_path = tmp_path / "short.wav"
        _create_wav(wav_path, duration=0.05, amplitude=0.3)
        passed, score = check_audio_quality(wav_path)
        assert not passed

    def test_nonexistent_file(self):
        passed, score = check_audio_quality(Path("/nonexistent.wav"))
        assert not passed
        assert score == 0.0


class TestTextQuality:
    def test_good_text(self, tmp_path: Path):
        txt_path = tmp_path / "good.txt"
        txt_path.write_text("This is a good text with enough content to pass quality checks. Adding more text to reach the threshold for a passing score.")
        passed, score = check_text_quality(txt_path)
        assert passed

    def test_empty_text(self, tmp_path: Path):
        txt_path = tmp_path / "empty.txt"
        txt_path.write_text("hi")
        passed, score = check_text_quality(txt_path)
        assert not passed


class TestRunQualityCheck:
    def test_audio_asset(self, tmp_path: Path):
        wav_path = tmp_path / "test.wav"
        _create_wav(wav_path)
        asset = Asset(
            id="test", agent="test", type="audio/wav",
            path=str(wav_path), monetization="direct_sale",
        )
        passed, score = run_quality_check(asset)
        assert passed

    def test_unknown_type(self, tmp_path: Path):
        path = tmp_path / "test.xyz"
        path.write_text("data")
        asset = Asset(
            id="test", agent="test", type="application/octet-stream",
            path=str(path), monetization="direct_sale",
        )
        passed, score = run_quality_check(asset)
        assert passed  # ファイル存在チェックのみ
