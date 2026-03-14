#!/bin/bash
# VRChat Tools Kit リポジトリ作成スクリプト
# 使い方: ./create-repo.sh [リポジトリ名] [作成先ディレクトリ]

REPO_NAME="${1:-vrchat-tools-kit}"
TARGET_DIR="${2:-$HOME/$REPO_NAME}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/new-repo-template"

echo "=== VRChat Tools Kit リポジトリ作成 ==="
echo "リポジトリ名: $REPO_NAME"
echo "作成先: $TARGET_DIR"
echo ""

# テンプレートの存在確認
if [ ! -d "$TEMPLATE_DIR" ]; then
    echo "エラー: テンプレートディレクトリが見つかりません: $TEMPLATE_DIR"
    exit 1
fi

# 作成先の重複チェック
if [ -d "$TARGET_DIR" ]; then
    echo "エラー: ディレクトリが既に存在します: $TARGET_DIR"
    exit 1
fi

# テンプレートをコピー
echo "1. テンプレートをコピー中..."
cp -r "$TEMPLATE_DIR" "$TARGET_DIR"

# git初期化
echo "2. gitリポジトリを初期化中..."
cd "$TARGET_DIR"
git init
git add -A
git commit -m "初期構成: VRChat OSCツールキットのテンプレート"

echo ""
echo "=== 作成完了 ==="
echo ""
echo "次のステップ:"
echo "  cd $TARGET_DIR"
echo ""
echo "GitHub上にリポジトリを作成してプッシュする場合:"
echo "  1. https://github.com/new でリポジトリを作成"
echo "  2. 以下のコマンドを実行:"
echo "     git remote add origin https://github.com/<ユーザー名>/$REPO_NAME.git"
echo "     git branch -M main"
echo "     git push -u origin main"
echo ""
echo "新しいツールを追加する場合:"
echo "  mkdir tools/<ツール名>"
echo "  # tools/<ツール名>/main.py を作成"
echo "  # tools/<ツール名>/README.md を作成"
