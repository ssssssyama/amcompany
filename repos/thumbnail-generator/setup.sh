#!/bin/bash
echo "========================================"
echo "  サムネイル生成ツール セットアップ"
echo "========================================"
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "[エラー] Pythonが見つかりません。"
    exit 1
fi
echo "[OK] $($PYTHON --version) が見つかりました"
$PYTHON -m pip install -r requirements.txt
echo "[OK] セットアップ完了！"
