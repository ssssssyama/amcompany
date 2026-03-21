"""
物件写真AIエンハンサー — 不動産物件写真をAIで一括高品質化

不動産ポータル掲載用の物件写真を自動で高品質化します。
Real-ESRGANによる高画質化、明るさ・コントラスト自動補正、
曇天→青空置換、プライバシーブラー（顔検出）に対応。

使い方:
  python enhance.py photo.jpg                      # 1枚を全処理
  python enhance.py ./photos/                      # フォルダ一括処理
  python enhance.py photo.jpg --no-upscale         # 高画質化をスキップ
  python enhance.py photo.jpg --no-sky             # 青空置換をスキップ
  python enhance.py photo.jpg --no-blur            # プライバシーブラーをスキップ
  python enhance.py photo.jpg --no-adjust          # 明るさ補正をスキップ
  python enhance.py photo.jpg --device cpu         # CPUで実行
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

# 共通ユーティリティ
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.error_handler import friendly_error_handler

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}

# OpenCV Haar cascade（顔検出用）
FACE_CASCADE_PATH = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"


# ---------------------------------------------------------------------------
# 1. 高画質化（Real-ESRGAN）
# ---------------------------------------------------------------------------

def upscale_image(img: np.ndarray, device: str = "cuda", max_size: int = 4096) -> np.ndarray:
    """Real-ESRGANで画像を高画質化（x4plus写実モデル）"""
    import torch
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer
    from common.gpu_utils import resolve_device

    device, gpu_info = resolve_device(device)
    use_half = not gpu_info["is_amd"]

    model = RRDBNet(
        num_in_ch=3, num_out_ch=3, num_feat=64,
        num_block=23, num_grow_ch=32, scale=4,
    )
    upscaler = RealESRGANer(
        scale=4,
        model_path="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
        model=model,
        tile=0, tile_pad=10, pre_pad=0,
        half=use_half and device == "cuda",
        gpu_id=0 if device == "cuda" else None,
    )

    output, _ = upscaler.enhance(img, outscale=4)

    # 最大サイズ制限
    out_h, out_w = output.shape[:2]
    if max_size > 0 and max(out_h, out_w) > max_size:
        scale_factor = max_size / max(out_h, out_w)
        new_w = int(out_w * scale_factor)
        new_h = int(out_h * scale_factor)
        output = cv2.resize(output, (new_w, new_h), interpolation=cv2.INTER_AREA)

    return output


# ---------------------------------------------------------------------------
# 2. 明るさ・コントラスト・ホワイトバランス自動補正
# ---------------------------------------------------------------------------

def auto_adjust(img: np.ndarray) -> np.ndarray:
    """明るさ・コントラスト・ホワイトバランスを自動補正"""
    # Gray World ホワイトバランス補正
    img = _gray_world_wb(img)

    # CLAHE（Contrast Limited Adaptive Histogram Equalization）
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)

    lab = cv2.merge([l_channel, a_channel, b_channel])
    img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # 明るさの底上げ（暗すぎる室内写真用）
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    v_mean = hsv[:, :, 2].mean()
    if v_mean < 100:
        # 暗い画像は明るさを持ち上げる
        boost = min(40, int(120 - v_mean))
        hsv[:, :, 2] = np.clip(hsv[:, :, 2].astype(np.int16) + boost, 0, 255).astype(np.uint8)
        img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    return img


def _gray_world_wb(img: np.ndarray) -> np.ndarray:
    """Gray Worldアルゴリズムによるホワイトバランス補正"""
    avg_b = img[:, :, 0].mean()
    avg_g = img[:, :, 1].mean()
    avg_r = img[:, :, 2].mean()
    avg_all = (avg_b + avg_g + avg_r) / 3.0

    if avg_b == 0 or avg_g == 0 or avg_r == 0:
        return img

    result = img.astype(np.float32)
    result[:, :, 0] *= avg_all / avg_b
    result[:, :, 1] *= avg_all / avg_g
    result[:, :, 2] *= avg_all / avg_r

    return np.clip(result, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# 3. 青空置換（曇天の外観写真 → 晴天に）
# ---------------------------------------------------------------------------

def replace_sky(img: np.ndarray, sky_ratio: float = 0.4) -> np.ndarray:
    """画像上部の曇天領域を青空グラデーションに置換

    Args:
        img: BGR画像
        sky_ratio: 空の検出対象とする画像上部の割合（デフォルト40%）
    """
    h, w = img.shape[:2]
    sky_h = int(h * sky_ratio)

    if sky_h < 10:
        return img

    # 上部領域のみ処理
    top_region = img[:sky_h, :]

    # HSVに変換して空領域を検出
    hsv = cv2.cvtColor(top_region, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    # 曇天の特徴: 低彩度 + 高明度（灰色〜白色の空）
    # または薄い青（色相80-130, 低彩度）
    overcast_mask = (
        ((sat < 50) & (val > 150)) |  # 白〜灰色の空
        ((hue > 80) & (hue < 130) & (sat < 80) & (val > 120))  # 薄い曇り空
    ).astype(np.uint8) * 255

    # モルフォロジー処理でマスクを整える
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    overcast_mask = cv2.morphologyEx(overcast_mask, cv2.MORPH_CLOSE, kernel)
    overcast_mask = cv2.morphologyEx(overcast_mask, cv2.MORPH_OPEN, kernel)

    # 空領域が十分でなければスキップ（全体の30%未満）
    sky_pixel_ratio = overcast_mask.sum() / (255.0 * sky_h * w)
    if sky_pixel_ratio < 0.3:
        return img

    # 青空グラデーション生成
    blue_sky = _create_blue_sky_gradient(w, sky_h)

    # エッジをぼかしてなじませる
    mask_blurred = cv2.GaussianBlur(overcast_mask, (21, 21), 10)
    mask_float = mask_blurred.astype(np.float32) / 255.0
    mask_3ch = np.stack([mask_float] * 3, axis=-1)

    # ブレンド
    blended = (blue_sky * mask_3ch + top_region.astype(np.float32) * (1 - mask_3ch))
    result = img.copy()
    result[:sky_h, :] = np.clip(blended, 0, 255).astype(np.uint8)

    return result


def _create_blue_sky_gradient(width: int, height: int) -> np.ndarray:
    """青空のグラデーション画像を生成（BGR）"""
    # 上: 深い青 → 下: 明るい水色
    top_color = np.array([210, 150, 80], dtype=np.float32)   # BGR: 明るい青
    bottom_color = np.array([235, 206, 160], dtype=np.float32)  # BGR: 薄い水色

    gradient = np.zeros((height, width, 3), dtype=np.float32)
    for y in range(height):
        t = y / max(height - 1, 1)
        gradient[y, :] = top_color * (1 - t) + bottom_color * t

    return gradient


# ---------------------------------------------------------------------------
# 4. プライバシーブラー（顔検出）
# ---------------------------------------------------------------------------

def privacy_blur(img: np.ndarray) -> np.ndarray:
    """顔を検出してぼかし処理を適用"""
    face_cascade = cv2.CascadeClassifier(FACE_CASCADE_PATH)
    if face_cascade.empty():
        print("  警告: 顔検出モデルが見つかりません。プライバシーブラーをスキップします。")
        return img

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30),
    )

    if len(faces) == 0:
        return img

    result = img.copy()
    for (x, y, w, h) in faces:
        # 検出領域を少し広げる
        pad = int(max(w, h) * 0.2)
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(result.shape[1], x + w + pad)
        y2 = min(result.shape[0], y + h + pad)

        # ガウシアンブラー
        roi = result[y1:y2, x1:x2]
        ksize = max(31, (max(w, h) // 3) | 1)  # 奇数にする
        result[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (ksize, ksize), 30)

    print(f"  {len(faces)}件の顔を検出してぼかし処理を適用しました")
    return result


# ---------------------------------------------------------------------------
# バッチ処理
# ---------------------------------------------------------------------------

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


def process_image(
    input_path: Path,
    output_path: Path,
    do_upscale: bool = True,
    do_adjust: bool = True,
    do_sky: bool = True,
    do_blur: bool = True,
    device: str = "cuda",
    max_size: int = 4096,
) -> bool:
    """1枚の画像を処理パイプラインに通す"""
    try:
        img = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
        if img is None:
            print(f"  エラー: 読み込めません — {input_path}")
            return False

        h, w = img.shape[:2]
        steps = []

        # パイプライン実行
        if do_adjust:
            img = auto_adjust(img)
            steps.append("補正")

        if do_sky:
            img = replace_sky(img)
            steps.append("青空")

        if do_blur:
            img = privacy_blur(img)
            steps.append("ブラー")

        if do_upscale:
            img = upscale_image(img, device=device, max_size=max_size)
            steps.append("高画質化")

        # 保存
        output_path.parent.mkdir(parents=True, exist_ok=True)
        out_h, out_w = img.shape[:2]
        cv2.imwrite(str(output_path), img, [cv2.IMWRITE_JPEG_QUALITY, 95])

        step_str = "→".join(steps) if steps else "無処理"
        print(f"  {w}x{h} → {out_w}x{out_h}  [{step_str}]  {output_path.name}")
        return True

    except Exception as e:
        print(f"  エラー: {input_path.name} — {e}")
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@friendly_error_handler("物件写真AIエンハンサー")
def main():
    parser = argparse.ArgumentParser(
        description="物件写真AIエンハンサー — 不動産物件写真をAIで一括高品質化"
    )
    parser.add_argument("input", type=str, help="入力ファイル or フォルダ")
    parser.add_argument("--output", type=str, default=None,
                        help="出力先ディレクトリ（デフォルト: 入力と同じ場所に _enhanced サフィックス）")
    parser.add_argument("--no-upscale", action="store_true", help="高画質化をスキップ")
    parser.add_argument("--no-adjust", action="store_true", help="明るさ・コントラスト補正をスキップ")
    parser.add_argument("--no-sky", action="store_true", help="青空置換をスキップ")
    parser.add_argument("--no-blur", action="store_true", help="プライバシーブラーをスキップ")
    parser.add_argument("--max-size", type=int, default=4096,
                        help="高画質化後の最大ピクセルサイズ（デフォルト: 4096, 0=制限なし）")
    parser.add_argument("--device", type=str, default="cuda", choices=["cuda", "cpu"],
                        help="使用デバイス（デフォルト: cuda）")

    args = parser.parse_args()

    input_path = Path(args.input)
    images = collect_images(input_path)

    if not images:
        print("処理する画像が見つかりません")
        return

    # 出力先決定
    if args.output:
        output_dir = Path(args.output)
    elif input_path.is_dir():
        output_dir = input_path.parent / f"{input_path.name}_enhanced"
    else:
        output_dir = input_path.parent / "enhanced"

    # 処理内容の表示
    steps = []
    if not args.no_adjust:
        steps.append("明るさ・コントラスト補正")
    if not args.no_sky:
        steps.append("青空置換")
    if not args.no_blur:
        steps.append("プライバシーブラー")
    if not args.no_upscale:
        steps.append("AI高画質化（Real-ESRGAN）")

    print("物件写真AIエンハンサー")
    print(f"  処理内容: {' → '.join(steps) if steps else 'なし'}")
    print(f"  入力: {input_path}")
    print(f"  出力: {output_dir}")
    print(f"  対象: {len(images)}ファイル")
    print()

    # バッチ処理
    success = 0
    for i, img_path in enumerate(images, 1):
        print(f"[{i}/{len(images)}] {img_path.name}")

        if input_path.is_file():
            out_name = f"{img_path.stem}_enhanced{img_path.suffix}"
        else:
            out_name = img_path.name

        out_path = output_dir / out_name

        if process_image(
            img_path, out_path,
            do_upscale=not args.no_upscale,
            do_adjust=not args.no_adjust,
            do_sky=not args.no_sky,
            do_blur=not args.no_blur,
            device=args.device,
            max_size=args.max_size,
        ):
            success += 1

    print(f"\n完了! {success}/{len(images)} ファイルを {output_dir} に出力しました")

    if not args.no_sky:
        print("\n※ 青空置換を使用した画像は、掲載時にCG加工済みである旨を表示してください（不動産公正競争規約）")


if __name__ == "__main__":
    main()
