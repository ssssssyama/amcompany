#!/bin/bash
echo "========================================"
echo "  テクスチャ高画質化ツール セットアップ"
echo "========================================"
echo ""
echo "※ GPU推奨（NVIDIA CUDA / AMD ROCm）。CPUでも動作しますが低速です。"
echo ""
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "[エラー] Pythonが見つかりません。"
    exit 1
fi
echo "[OK] $($PYTHON --version) が見つかりました"
echo "パッケージをインストール中..."
$PYTHON -m pip install -r requirements.txt
echo ""
echo "[OK] セットアップ完了！"
