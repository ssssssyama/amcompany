"""
足音AI生成ツール — Stable Audio Open を使った足音効果音ジェネレーター

VRChat アバター用の足音ギミックに使える効果音を AI でローカル生成します。
GPU（NVIDIA CUDA / AMD ROCm 対応）が必要です。初回実行時にモデル（約3.5GB）を自動ダウンロードします。

使い方:
  python generate.py                    # 全サーフェスの足音を生成
  python generate.py --surfaces wood stone  # 指定サーフェスのみ
  python generate.py --variations 5     # 各サーフェス5バリエーション
  python generate.py --duration 1.0     # 1秒の足音
  python generate.py --output ./my_sounds  # 出力先指定
"""

import argparse
import json
import os
import sys
from pathlib import Path

import torch
import torchaudio
from einops import rearrange
from stable_audio_tools import get_pretrained_model
from stable_audio_tools.inference.generation import generate_diffusion_cond

# 共通GPU検出ユーティリティ
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.gpu_utils import detect_gpu, resolve_device


# サーフェス別プロンプト定義
SURFACE_PROMPTS = {
    "wood": {
        "name_ja": "木の床",
        "prompt": "single footstep on wooden floor, indoor, clear, close-up, foley",
    },
    "stone": {
        "name_ja": "石畳",
        "prompt": "single footstep on stone floor, indoor, clear, close-up, foley",
    },
    "grass": {
        "name_ja": "草地",
        "prompt": "single footstep on grass, outdoor, soft, close-up, foley",
    },
    "metal": {
        "name_ja": "金属",
        "prompt": "single footstep on metal grating, industrial, resonant, close-up, foley",
    },
    "gravel": {
        "name_ja": "砂利",
        "prompt": "single footstep on gravel, crunchy, outdoor, close-up, foley",
    },
    "snow": {
        "name_ja": "雪",
        "prompt": "single footstep on snow, soft crunch, winter, close-up, foley",
    },
    "water": {
        "name_ja": "水たまり",
        "prompt": "single footstep splashing in shallow water puddle, close-up, foley",
    },
    "carpet": {
        "name_ja": "カーペット",
        "prompt": "single soft footstep on carpet, indoor, muffled, close-up, foley",
    },
    "sand": {
        "name_ja": "砂浜",
        "prompt": "single footstep on sand, beach, soft, close-up, foley",
    },
    "tile": {
        "name_ja": "タイル",
        "prompt": "single footstep on ceramic tile floor, indoor, sharp, close-up, foley",
    },
}


def load_model(device: str = "cuda"):
    """Stable Audio Open モデルを読み込む"""
    print("モデルを読み込み中... (初回はダウンロードに数分かかります)")
    model, model_config = get_pretrained_model("stabilityai/stable-audio-open-1.0")
    model = model.to(device)
    print("モデル読み込み完了")
    return model, model_config


def generate_footstep(
    model,
    model_config: dict,
    prompt: str,
    duration: float = 0.5,
    seed: int = -1,
    device: str = "cuda",
    force_fp32: bool = False,
) -> torch.Tensor:
    """1つの足音を生成する"""
    sample_rate = model_config["sample_rate"]
    sample_size = model_config["sample_size"]

    if seed < 0:
        seed = torch.randint(0, 2**32 - 1, (1,)).item()

    conditioning = [
        {
            "prompt": prompt,
            "seconds_start": 0,
            "seconds_total": duration,
        }
    ]

    # AMD GPUではfp16でNaNが出る場合があるためfp32を強制
    ctx = torch.autocast(device_type="cuda", dtype=torch.float32) if force_fp32 else torch.no_grad()

    with torch.no_grad(), ctx:
        output = generate_diffusion_cond(
            model,
            steps=100,
            cfg_scale=7,
            conditioning=conditioning,
            sample_size=sample_size,
            sigma_min=0.3,
            sigma_max=500,
            sampler_type="dpmpp-3m-sde",
            device=device,
            seed=seed,
        )

    # shape: (batch, channels, samples) -> (channels, samples)
    output = rearrange(output, "b d n -> d (b n)")

    # ピーク正規化
    peak = output.abs().max()
    if peak > 0:
        output = output / peak * 0.9

    return output, sample_rate


def trim_silence(audio: torch.Tensor, sample_rate: int, threshold: float = 0.01) -> torch.Tensor:
    """先頭と末尾の無音をトリミング"""
    abs_audio = audio.abs().max(dim=0).values
    mask = abs_audio > threshold

    if not mask.any():
        return audio

    nonzero = mask.nonzero()
    start = max(0, nonzero[0].item() - int(sample_rate * 0.01))  # 10ms マージン
    end = min(audio.shape[-1], nonzero[-1].item() + int(sample_rate * 0.05))  # 50ms マージン

    return audio[:, start:end]


def generate_all(
    surfaces: list[str],
    variations: int = 3,
    duration: float = 0.5,
    output_dir: str = "./output",
    device: str = "cuda",
    force_fp32: bool = False,
):
    """全サーフェスの足音を一括生成"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    model, model_config = load_model(device)
    sample_rate = model_config["sample_rate"]

    manifest = {}
    total = len(surfaces) * variations
    current = 0

    for surface in surfaces:
        if surface not in SURFACE_PROMPTS:
            print(f"警告: 不明なサーフェス '{surface}' をスキップ")
            continue

        info = SURFACE_PROMPTS[surface]
        surface_dir = output_path / surface
        surface_dir.mkdir(exist_ok=True)

        manifest[surface] = {
            "name_ja": info["name_ja"],
            "files": [],
        }

        for i in range(variations):
            current += 1
            print(f"[{current}/{total}] {info['name_ja']} ({surface}) - バリエーション {i + 1}")

            audio, sr = generate_footstep(
                model, model_config, info["prompt"],
                duration=duration, device=device, force_fp32=force_fp32,
            )

            # 無音トリミング
            audio = trim_silence(audio, sr)

            # 保存
            filename = f"{surface}_{i + 1:02d}.wav"
            filepath = surface_dir / filename
            torchaudio.save(str(filepath), audio.cpu(), sr)

            manifest[surface]["files"].append(filename)
            print(f"  → {filepath} ({audio.shape[-1] / sr:.2f}秒)")

    # マニフェスト保存
    manifest_path = output_path / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n生成完了! {current}ファイルを {output_path} に出力しました")
    print(f"マニフェスト: {manifest_path}")


def main():
    parser = argparse.ArgumentParser(
        description="足音AI生成ツール — Stable Audio Open で足音効果音を生成"
    )
    parser.add_argument(
        "--surfaces",
        nargs="+",
        default=list(SURFACE_PROMPTS.keys()),
        choices=list(SURFACE_PROMPTS.keys()),
        help="生成するサーフェスの種類 (デフォルト: 全種類)",
    )
    parser.add_argument(
        "--variations",
        type=int,
        default=3,
        help="各サーフェスのバリエーション数 (デフォルト: 3)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0.5,
        help="生成する音の長さ（秒） (デフォルト: 0.5)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./output",
        help="出力ディレクトリ (デフォルト: ./output)",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cuda",
        choices=["cuda", "cpu"],
        help="使用デバイス (デフォルト: cuda)。NVIDIA/AMD両方 'cuda' で動作",
    )
    parser.add_argument(
        "--precision",
        type=str,
        default="auto",
        choices=["auto", "fp32", "fp16"],
        help="演算精度 (デフォルト: auto)。AMD GPUではauto時にfp32を使用",
    )
    parser.add_argument(
        "--list-surfaces",
        action="store_true",
        help="利用可能なサーフェス一覧を表示",
    )

    args = parser.parse_args()

    if args.list_surfaces:
        print("利用可能なサーフェス:")
        for key, info in SURFACE_PROMPTS.items():
            print(f"  {key:10s} — {info['name_ja']}")
        return

    # GPU検出
    args.device, gpu_info = resolve_device(args.device)

    # precision決定
    force_fp32 = False
    if args.precision == "fp32":
        force_fp32 = True
    elif args.precision == "auto" and gpu_info["is_amd"]:
        print("AMD GPU: NaN防止のためfp32モードを使用します")
        force_fp32 = True

    generate_all(
        surfaces=args.surfaces,
        variations=args.variations,
        duration=args.duration,
        output_dir=args.output,
        device=args.device,
        force_fp32=force_fp32,
    )


if __name__ == "__main__":
    main()
