# テクスチャ高画質化ツール

Real-ESRGAN を使って、VRChatアバターの低解像度テクスチャを高画質にアップスケールするツール。

## 必要環境

- Python 3.9+
- GPU（推奨。CPUでも動作するが低速）
  - **NVIDIA**: CUDA対応GPU
  - **AMD**: ROCm 6.1+ 対応GPU（RX 7900 XTX等）
- VRAM: 2GB以上（4096px出力でも4GB程度）

## セットアップ

### NVIDIA GPU

```bash
pip install -r requirements-upscaler.txt
```

### AMD GPU (ROCm)

```bash
# 1. ROCm版PyTorchをインストール
pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm6.1

# 2. 残りの依存パッケージ
pip install realesrgan opencv-python Pillow
```

### Windows (WSL2 + AMD GPU)

```bash
export HSA_OVERRIDE_GFX_VERSION=11.0.0  # RX 7900 XTX の場合
pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm6.1
pip install realesrgan opencv-python Pillow
```

初回実行時にモデル（約65MB）が自動ダウンロードされます。

## 使い方

```bash
# 単体ファイルをアップスケール
python tools/texture-upscaler/upscale.py avatar_texture.png

# フォルダ内を一括処理
python tools/texture-upscaler/upscale.py ./textures/

# 2倍にアップスケール（デフォルトは4倍）
python tools/texture-upscaler/upscale.py image.png --scale 2

# 最大4096pxで出力（デフォルトは2048px）
python tools/texture-upscaler/upscale.py image.png --max-size 4096

# 法線マップをアップスケール
python tools/texture-upscaler/upscale.py normal_map.png --normal-map

# 写実モデルを使用（デフォルトはアニメ調）
python tools/texture-upscaler/upscale.py image.png --model x4plus

# 出力先を指定
python tools/texture-upscaler/upscale.py image.png --output ./output/

# 利用可能なモデル一覧
python tools/texture-upscaler/upscale.py --list-models dummy
```

## モデル

| ID | 説明 | 推奨用途 |
|----|------|----------|
| x4plus-anime | アニメ調テクスチャ向け（デフォルト） | VRChatアバター全般 |
| x4plus | 写実的テクスチャ向け | フォトリアル系アバター・ワールド |

## VRChat テクスチャサイズの目安

| 解像度 | パフォーマンス | 推奨用途 |
|--------|--------------|----------|
| 1024px | Excellent | モバイル・Quest向け |
| 2048px | Good | PC向けスタンダード |
| 4096px | Medium | 高品質PC向け（容量注意） |

**推奨**: 2048px（`--max-size 2048`）が品質とパフォーマンスのバランスが最適です。

## 対応フォーマット

入力: PNG, JPG, TGA, BMP, TIFF, WebP
出力: PNG（常にPNGで出力、アルファチャンネル保持）

## ライセンス

- **Real-ESRGAN**: BSD-3-Clause（商用利用・再配布OK）
- **生成された画像**: ユーザーが自由に利用可能
