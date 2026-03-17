#!/usr/bin/env bash
# ツールごとのリポジトリ分割スクリプト
# 使い方: bash split_repos.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/tools"
OUT="$SCRIPT_DIR/split-output"

echo "========================================"
echo "  amcompany リポジトリ分割スクリプト"
echo "========================================"
echo "出力先: $OUT"
echo ""

# 出力ディレクトリ初期化
rm -rf "$OUT"
mkdir -p "$OUT"

# --- 共通 .gitignore ---
GITIGNORE_CONTENT="__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.env
"

# ========================================
# 1. amcompany-common (独立パッケージ)
# ========================================
echo "[1/8] amcompany-common"
COMMON_DIR="$OUT/amcompany-common"
mkdir -p "$COMMON_DIR/amcompany_common"

cp "$SRC/common/__init__.py" "$COMMON_DIR/amcompany_common/__init__.py"
cp "$SRC/common/osc_client.py" "$COMMON_DIR/amcompany_common/osc_client.py"
cp "$SRC/common/error_handler.py" "$COMMON_DIR/amcompany_common/error_handler.py"
cp "$SRC/common/gpu_utils.py" "$COMMON_DIR/amcompany_common/gpu_utils.py"

# error_handler.py 内の requirements 参照を修正
sed -i 's|requirements-footstep\.txt|requirements.txt|g' "$COMMON_DIR/amcompany_common/error_handler.py"
sed -i 's|requirements-upscaler\.txt|requirements.txt|g' "$COMMON_DIR/amcompany_common/error_handler.py"

# pyproject.toml 生成
cat > "$COMMON_DIR/pyproject.toml" << 'PYPROJECT'
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "amcompany-common"
version = "0.1.0"
description = "amcompany ツール共通ユーティリティ（OSCクライアント、GPU検出、エラーハンドラー）"
requires-python = ">=3.10"

[project.optional-dependencies]
osc = ["python-osc>=1.8.0"]
gpu = ["torch>=2.1.0"]
PYPROJECT

# README.md
cat > "$COMMON_DIR/README.md" << 'README'
# amcompany-common

amcompany ツール群の共通ユーティリティパッケージです。

## モジュール

- `osc_client` — VRChat OSC 通信クライアント
- `error_handler` — 日本語エラーメッセージハンドラー
- `gpu_utils` — GPU 検出ユーティリティ（NVIDIA / AMD ROCm / CPU）

## インストール

```bash
pip install -e .                 # 基本インストール
pip install -e ".[osc]"          # OSC機能を含む
pip install -e ".[gpu]"          # GPU機能を含む
```
README

echo "$GITIGNORE_CONTENT" > "$COMMON_DIR/.gitignore"

# ========================================
# 2. amcompany-chatbox-decorator
# ========================================
echo "[2/8] amcompany-chatbox-decorator"
CBD_DIR="$OUT/amcompany-chatbox-decorator"
mkdir -p "$CBD_DIR"

cp "$SRC/chatbox-decorator/main.py" "$CBD_DIR/main.py"
cp "$SRC/chatbox-decorator/chatbox-decorator.bat" "$CBD_DIR/chatbox-decorator.bat"
cp "$SRC/chatbox-decorator/README.md" "$CBD_DIR/README.md"
echo "$GITIGNORE_CONTENT" > "$CBD_DIR/.gitignore"

# import 修正
sed -i '/^sys\.path\.insert(0, os\.path\.join(os\.path\.dirname(__file__), "\.\."))$/d' "$CBD_DIR/main.py"
sed -i 's/from common\./from amcompany_common./g' "$CBD_DIR/main.py"
# 不要になった import を削除 (os が common の sys.path.insert のためだけに使われている場合)
# chatbox-decorator は os を他で使っていないので削除
sed -i '/^import os$/d' "$CBD_DIR/main.py"

cat > "$CBD_DIR/requirements.txt" << 'REQ'
python-osc>=1.8.0
amcompany-common
REQ

# ========================================
# 3. amcompany-omikuji-bot
# ========================================
echo "[3/8] amcompany-omikuji-bot"
OMK_DIR="$OUT/amcompany-omikuji-bot"
mkdir -p "$OMK_DIR"

cp "$SRC/omikuji-bot/main.py" "$OMK_DIR/main.py"
cp "$SRC/omikuji-bot/omikuji-bot.bat" "$OMK_DIR/omikuji-bot.bat"
cp "$SRC/omikuji-bot/README.md" "$OMK_DIR/README.md"
echo "$GITIGNORE_CONTENT" > "$OMK_DIR/.gitignore"

# import 修正
sed -i '/^sys\.path\.insert(0, os\.path\.join(os\.path\.dirname(__file__), "\.\."))$/d' "$OMK_DIR/main.py"
sed -i 's/from common\./from amcompany_common./g' "$OMK_DIR/main.py"
# omikuji-bot は os を他で使っていないので削除
sed -i '/^import os$/d' "$OMK_DIR/main.py"

cat > "$OMK_DIR/requirements.txt" << 'REQ'
python-osc>=1.8.0
amcompany-common
REQ

# ========================================
# 4. amcompany-osc-timer
# ========================================
echo "[4/8] amcompany-osc-timer"
OSC_DIR="$OUT/amcompany-osc-timer"
mkdir -p "$OSC_DIR"

cp "$SRC/osc-timer/main.py" "$OSC_DIR/main.py"
cp "$SRC/osc-timer/osc-timer.bat" "$OSC_DIR/osc-timer.bat"
cp "$SRC/osc-timer/README.md" "$OSC_DIR/README.md"
echo "$GITIGNORE_CONTENT" > "$OSC_DIR/.gitignore"

# import 修正
sed -i '/^sys\.path\.insert(0, os\.path\.join(os\.path\.dirname(__file__), "\.\."))$/d' "$OSC_DIR/main.py"
sed -i 's/from common\./from amcompany_common./g' "$OSC_DIR/main.py"
# osc-timer は os を他で使っていないので削除
sed -i '/^import os$/d' "$OSC_DIR/main.py"

cat > "$OSC_DIR/requirements.txt" << 'REQ'
python-osc>=1.8.0
amcompany-common
REQ

# ========================================
# 5. amcompany-texture-upscaler
# ========================================
echo "[5/8] amcompany-texture-upscaler"
TU_DIR="$OUT/amcompany-texture-upscaler"
mkdir -p "$TU_DIR"

cp "$SRC/texture-upscaler/upscale.py" "$TU_DIR/upscale.py"
cp "$SRC/texture-upscaler/texture-upscaler.bat" "$TU_DIR/texture-upscaler.bat"
cp "$SRC/texture-upscaler/README.md" "$TU_DIR/README.md"
echo "$GITIGNORE_CONTENT" > "$TU_DIR/.gitignore"

# import 修正
sed -i '/^sys\.path\.insert(0, str(Path(__file__)\.resolve()\.parent\.parent))$/d' "$TU_DIR/upscale.py"
sed -i 's/from common\./from amcompany_common./g' "$TU_DIR/upscale.py"
# sys が他で使われていないか確認: upscale.py は sys を他で使っていないので削除
sed -i '/^import sys$/d' "$TU_DIR/upscale.py"
# "# 共通GPU検出ユーティリティ" コメント行も削除
sed -i '/^# 共通GPU検出ユーティリティ$/d' "$TU_DIR/upscale.py"

cat > "$TU_DIR/requirements.txt" << 'REQ'
torch>=2.1.0
realesrgan>=0.3.0
opencv-python>=4.8.0
Pillow>=10.0.0
amcompany-common
REQ

# ========================================
# 6. amcompany-footstep-generator
# ========================================
echo "[6/8] amcompany-footstep-generator"
FG_DIR="$OUT/amcompany-footstep-generator"
mkdir -p "$FG_DIR"

cp "$SRC/footstep-generator/generate.py" "$FG_DIR/generate.py"
cp "$SRC/footstep-generator/README.md" "$FG_DIR/README.md"
echo "$GITIGNORE_CONTENT" > "$FG_DIR/.gitignore"

# import 修正
sed -i '/^sys\.path\.insert(0, str(Path(__file__)\.resolve()\.parent\.parent))$/d' "$FG_DIR/generate.py"
sed -i 's/from common\./from amcompany_common./g' "$FG_DIR/generate.py"
# sys が他で使われていないか確認: generate.py は sys を他で使っていないので削除
sed -i '/^import sys$/d' "$FG_DIR/generate.py"
# "# 共通GPU検出ユーティリティ" コメント行も削除
sed -i '/^# 共通GPU検出ユーティリティ$/d' "$FG_DIR/generate.py"

cat > "$FG_DIR/requirements.txt" << 'REQ'
torch>=2.1.0
torchaudio>=2.1.0
einops>=0.7.0
stable-audio-tools>=0.0.12
amcompany-common
REQ

# ========================================
# 7. amcompany-thumbnail-generator
# ========================================
echo "[7/8] amcompany-thumbnail-generator"
TG_DIR="$OUT/amcompany-thumbnail-generator"
mkdir -p "$TG_DIR"

cp "$SRC/thumbnail-generator/generate.py" "$TG_DIR/generate.py"
cp "$SRC/thumbnail-generator/thumbnail-generator.bat" "$TG_DIR/thumbnail-generator.bat"
cp "$SRC/thumbnail-generator/README.md" "$TG_DIR/README.md"
echo "$GITIGNORE_CONTENT" > "$TG_DIR/.gitignore"

cat > "$TG_DIR/requirements.txt" << 'REQ'
Pillow>=10.0.0
REQ

# ========================================
# 8. amcompany-test-evidence
# ========================================
echo "[8/8] amcompany-test-evidence"
TE_DIR="$OUT/amcompany-test-evidence"
mkdir -p "$TE_DIR"

# 全ファイル・ディレクトリをコピー
cp -r "$SRC/test-evidence/"* "$TE_DIR/"
# .gitignore があればコピー
if [ -f "$SRC/test-evidence/.gitignore" ]; then
    cp "$SRC/test-evidence/.gitignore" "$TE_DIR/.gitignore"
else
    echo "$GITIGNORE_CONTENT" > "$TE_DIR/.gitignore"
fi

# ========================================
# 各ディレクトリで git init + 初回コミット
# ========================================
echo ""
echo "Git リポジトリ初期化中..."

for repo_dir in "$OUT"/amcompany-*; do
    repo_name="$(basename "$repo_dir")"
    echo "  git init: $repo_name"
    (
        cd "$repo_dir"
        git init -q
        git add -A
        git commit -q -m "Initial commit: $repo_name (split from amcompany monorepo)"
    )
done

# ========================================
# 完了
# ========================================
echo ""
echo "========================================"
echo "  分割完了!"
echo "========================================"
echo ""
echo "出力先: $OUT"
echo ""
ls -1d "$OUT"/amcompany-* | while read dir; do
    echo "  $(basename "$dir")/"
done
echo ""
echo "各ツールで amcompany-common を利用するには:"
echo "  pip install -e ../amcompany-common"
