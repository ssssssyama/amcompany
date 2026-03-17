#!/bin/bash
echo "========================================"
echo "  AM Company ツール セットアップ"
echo "========================================"
echo ""

# Pythonの確認
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "[エラー] Pythonが見つかりません。"
        echo ""
        echo "Pythonをインストールしてください:"
        echo "  Mac:   brew install python3"
        echo "  Linux: sudo apt install python3 python3-pip"
        echo ""
        exit 1
    fi
    PYTHON=python
else
    PYTHON=python3
fi

PYVER=$($PYTHON --version 2>&1)
echo "[OK] $PYVER が見つかりました"
echo ""

# 基本パッケージのインストール
echo "--- VRChatツール用パッケージをインストール中 ---"
$PYTHON -m pip install python-osc Pillow
if [ $? -ne 0 ]; then
    echo "[エラー] パッケージのインストールに失敗しました。"
    exit 1
fi
echo ""
echo "[OK] VRChatツール用のセットアップが完了しました！"
echo ""

# オプション: AI系ツール
echo "========================================"
echo "  追加オプション"
echo "========================================"
echo ""
echo "AI系ツール（足音生成・テクスチャ高画質化）も"
echo "使いますか？（GPUが必要です）"
echo ""
read -p "インストールする場合は y を入力: " AI_CHOICE

if [ "$AI_CHOICE" = "y" ] || [ "$AI_CHOICE" = "Y" ]; then
    echo ""
    echo "--- AI系パッケージをインストール中 ---"
    echo "（数分かかる場合があります）"
    $PYTHON -m pip install -r requirements-upscaler.txt
    echo ""
    echo "[OK] テクスチャ高画質化ツールのセットアップ完了"
    echo ""
    echo "足音生成ツールも使う場合は別途以下を実行してください:"
    echo "  $PYTHON -m pip install -r requirements-footstep.txt"
fi

echo ""
echo "========================================"
echo "  セットアップ完了！"
echo "========================================"
echo ""
echo "ツールを起動するには:"
echo "  $PYTHON launcher.py"
echo ""
