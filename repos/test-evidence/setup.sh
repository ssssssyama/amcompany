#!/bin/bash
echo "========================================"
echo "  テストエビデンス自動化ツール セットアップ"
echo "========================================"
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "[エラー] Pythonが見つかりません。"
    exit 1
fi
echo "[OK] $($PYTHON --version) が見つかりました"
echo ""
echo "--- Pythonパッケージをインストール中 ---"
$PYTHON -m pip install -r requirements.txt
echo ""
echo "--- Playwrightブラウザをインストール中 ---"
$PYTHON -m playwright install chromium
echo ""
echo "[OK] セットアップ完了！"
echo "使い方: $PYTHON evidence_runner.py テスト仕様書.xlsx"
