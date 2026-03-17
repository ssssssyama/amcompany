#!/bin/bash
echo "========================================"
echo "  足音AI生成ツール セットアップ"
echo "========================================"
echo ""
echo "※ このツールにはNVIDIA GPU（CUDA）またはAMD GPU（ROCm）が必要です。"
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
echo "※ 初回実行時にモデル（約3.5GB）がダウンロードされます。"
