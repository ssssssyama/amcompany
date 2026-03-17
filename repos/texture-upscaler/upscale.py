"""
テクスチャ高画質化ツール — Real-ESRGAN でVRChat用テクスチャをアップスケール

VRChatアバターの低解像度テクスチャを高画質にアップスケールします。
NVIDIA / AMD (ROCm) GPU に対応。CPU でも動作します（低速）。

使い方:
  python upscale.py image.png                    # 単体ファイルをアップスケール
  python upscale.py ./textures/                  # フォルダ内を一括処理
  python upscale.py image.png --scale 2          # 2倍にアップスケール
  python upscale.py image.png --max-size 4096    # 最大4096pxに制限
  python upscale.py normal.png --normal-map      # 法線マップモード
  python upscale.py image.png --model x4plus     # 写実モデルを使用
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
import torch
from basicsr.archs.rrdbnet_arch import RRDBNet
from PIL import Image
from realesrgan import RealESRGANer

from lib.gpu_utils import detect_gpu, resolve_device

# 対応する画像拡張子
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tiff", ".webp"}

# モデル設定
MODELS = {
    "x4plus-anime": {
        "name_ja": "アニメ調（VRChat推奨）",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
        "num_block": 6,
        "scale": 4,
    },
    "x4plus": {
        "name_ja": "写実的",
        "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        "num_block": 23,
        "scale": 4,
    },
}


def create_upscaler(
    model_name: str = "x4plus-anime",
    device: str = "cuda",
    half: bool = True,
) -> RealESRGANer:
    """Real-ESRGANモデルを初期化"""
    model_info = MODELS[model_name]

    model = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        num_feat=64,
        num_block=model_info["num_block"],
        num_grow_ch=32,
        scale=model_info["scale"],
    )

    gpu_id = 0 if device == "cuda" else None

    upscaler = RealESRGANer(
        scale=model_info["scale"],
        model_path=model_info["url"],
        model=model,
        tile=0,
        tile_pad=10,
        pre_pad=0,
        half=half and device == "cuda",
        gpu_id=gpu_id,
    )

    return upscaler


def upscale_image(
    upscaler: RealESRGANer,
    input_path: Path,
    output_path: Path,
    target_scale: int = 4,
    max_size: int = 2048,
    is_normal_map: bool = False,
) -> bool:
    """1つの画像をアップスケールする"""
    try:
        img = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            print(f"  エラー: 読み込めません — {input_path}")
            return False

        h, w = img.shape[:2]

        # アップスケール実行
        output, _ = upscaler.enhance(img, outscale=target_scale)

        # 最大サイズ制限
        out_h, out_w = output.shape[:2]
        if max_size > 0 and max(out_h, out_w) > max_size:
            scale_factor = max_size / max(out_h, out_w)
            new_w = int(out_w * scale_factor)
            new_h = int(out_h * scale_factor)
            interpolation = cv2.INTER_AREA  # 縮小時は INTER_AREA が最適
            output = cv2.resize(output, (new_w, new_h), interpolation=interpolation)
            out_h, out_w = output.shape[:2]

        # 法線マップの後処理（正規化）
        if is_normal_map:
            output = _normalize_normal_map(output)

        # 保存（PNGで出力）
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), output)

        print(f"  {w}x{h} → {out_w}x{out_h}  {output_path}")
        return True

    except Exception as e:
        print(f"  エラー: {input_path} — {e}")
        return False


def _normalize_normal_map(img: np.ndarray) -> np.ndarray:
    """法線マップを正規化（各ピクセルの法線ベクトルを単位ベクトルに）"""
    img_float = img.astype(np.float32) / 255.0

    if img_float.shape[2] >= 3:
        # BGR -> XYZ (0~1 -> -1~1)
        normals = img_float[:, :, :3] * 2.0 - 1.0

        # 正規化
        length = np.sqrt(np.sum(normals**2, axis=2, keepdims=True))
        length = np.maximum(length, 1e-8)
        normals = normals / length

        # -1~1 -> 0~1 -> 0~255
        img_float[:, :, :3] = (normals + 1.0) / 2.0

    return (img_float * 255.0).clip(0, 255).astype(np.uint8)


def collect_images(input_path: Path) -> list[Path]:
    """入力パスから画像ファイルを収集"""
    if input_path.is_file():
        if input_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            return [input_path]
        print(f"非対応の形式: {input_path.suffix}")
        return []

    if input_path.is_dir():
        images = []
        for ext in SUPPORTED_EXTENSIONS:
            images.extend(input_path.glob(f"*{ext}"))
            images.extend(input_path.glob(f"*{ext.upper()}"))
        return sorted(set(images))

    print(f"パスが見つかりません: {input_path}")
    return []


def main():
    parser = argparse.ArgumentParser(
        description="テクスチャ高画質化ツール — Real-ESRGAN でVRChat用テクスチャをアップスケール"
    )
    parser.add_argument(
        "input",
        type=str,
        help="入力ファイル or フォルダ",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="出力先ディレクトリ (デフォルト: 入力と同じ場所に _upscaled サフィックス)",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=4,
        choices=[2, 4],
        help="アップスケール倍率 (デフォルト: 4)",
    )
    parser.add_argument(
        "--max-size",
        type=int,
        default=2048,
        help="出力の最大ピクセルサイズ (デフォルト: 2048, 0=制限なし)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="x4plus-anime",
        choices=list(MODELS.keys()),
        help="使用モデル (デフォルト: x4plus-anime)",
    )
    parser.add_argument(
        "--normal-map",
        action="store_true",
        help="法線マップモード（アップスケール後に法線ベクトルを正規化）",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cuda",
        choices=["cuda", "cpu"],
        help="使用デバイス (デフォルト: cuda)。NVIDIA/AMD両方 'cuda' で動作",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="利用可能なモデル一覧を表示",
    )

    args = parser.parse_args()

    if args.list_models:
        print("利用可能なモデル:")
        for key, info in MODELS.items():
            print(f"  {key:20s} — {info['name_ja']}")
        return

    # GPU検出
    device, gpu_info = resolve_device(args.device)

    # AMD GPUではfp16を無効化（NaN防止）
    use_half = not gpu_info["is_amd"]

    # 画像収集
    input_path = Path(args.input)
    images = collect_images(input_path)

    if not images:
        print("アップスケールする画像が見つかりません")
        return

    # 出力先決定
    if args.output:
        output_dir = Path(args.output)
    elif input_path.is_dir():
        output_dir = input_path.parent / f"{input_path.name}_upscaled"
    else:
        output_dir = input_path.parent

    # モデル初期化
    print(f"モデル読み込み中: {args.model} ({MODELS[args.model]['name_ja']})")
    upscaler = create_upscaler(
        model_name=args.model,
        device=device,
        half=use_half,
    )

    # アップスケール実行
    print(f"\n{len(images)}ファイルをアップスケール中...")
    if args.normal_map:
        print("法線マップモード: ON")

    success = 0
    for i, img_path in enumerate(images, 1):
        print(f"[{i}/{len(images)}] {img_path.name}")

        # 出力ファイルパス
        if input_path.is_file():
            stem = img_path.stem
            out_name = f"{stem}_upscaled.png"
        else:
            out_name = f"{img_path.stem}.png"

        out_path = output_dir / out_name

        if upscale_image(
            upscaler, img_path, out_path,
            target_scale=args.scale,
            max_size=args.max_size,
            is_normal_map=args.normal_map,
        ):
            success += 1

    print(f"\n完了! {success}/{len(images)} ファイルを {output_dir} に出力しました")


if __name__ == "__main__":
    main()
