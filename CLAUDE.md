# CLAUDE.md — AM Company ツール集

## プロジェクト概要

VRChat向けツール群とテストエビデンス自動化ツールをまとめたPythonモノレポ。
日本語ファーストのプロジェクトで、VRChatユーザーとSIer現場のQAエンジニアがターゲット。

- **言語**: Python 3.9+ (ツールにより3.10+)
- **GUI**: Tkinter (launcher.py)
- **ブラウザ自動化**: Playwright (async)
- **VRChat通信**: OSC (python-osc)
- **AI/GPU**: PyTorch, Real-ESRGAN, Stable Audio Open

## ディレクトリ構成

```
amcompany/
├── launcher.py                 # GUIランチャー (Tkinter) — メインエントリポイント
├── setup.bat / setup.sh        # セットアップスクリプト (Windows / Mac・Linux)
├── split_repos.sh              # モノレポ→独立パッケージ分割スクリプト
├── requirements.txt            # 共通依存 (python-osc, Pillow)
├── requirements-upscaler.txt   # テクスチャ高画質化用 (torch, realesrgan)
├── requirements-footstep.txt   # 足音AI生成用 (torch, stable-audio-tools)
├── docs/                       # 戦略・企画ドキュメント
│   ├── product-ideas.md        # BOOTH商品化戦略
│   ├── usability-barriers.md   # ユーザビリティ障壁分析
│   └── brainstorm.md           # 新規事業ブレスト
├── tools/
│   ├── common/                 # 共通ユーティリティ
│   │   ├── osc_client.py       #   OSCクライアント (VRChat通信)
│   │   ├── error_handler.py    #   日本語エラーハンドラ (@friendly_error_handler)
│   │   └── gpu_utils.py        #   GPU自動検出 (CUDA/ROCm)
│   ├── chatbox-decorator/      # Chatbox装飾ツール
│   ├── omikuji-bot/            # おみくじBot
│   ├── osc-timer/              # タイマー/ストップウォッチ/ポモドーロ
│   ├── texture-upscaler/       # AI画像アップスケーラー (Real-ESRGAN)
│   ├── footstep-generator/     # AI足音生成 (Stable Audio Open)
│   ├── thumbnail-generator/    # BOOTHサムネイル生成
│   └── test-evidence/          # テストエビデンス自動化スイート
│       ├── evidence_runner.py  #   メインテストエンジン (Playwright)
│       ├── project_config.py   #   YAML設定読み込み
│       ├── gen_spec.py         #   自然言語→テストステップ変換
│       ├── record2spec.py      #   ブラウザ録画→YAML変換
│       ├── text2spec.py        #   テキスト→Excel仕様書変換
│       ├── create_template.py  #   テンプレートExcel生成
│       ├── requirements.txt    #   専用依存 (playwright, openpyxl, pyyaml)
│       ├── vba-lite/           #   VBA Lite版 (無料配布)
│       ├── docker/             #   Docker Pro版 (有料)
│       ├── demo/               #   デモ環境
│       ├── examples/           #   設定・仕様書サンプル
│       └── tests/              #   pytest ユニットテスト
└── split-output/               # 分割済みパッケージ出力先
```

## 開発ワークフロー

### セットアップ

```bash
# 共通依存のインストール
pip install -r requirements.txt

# AI系ツールが必要な場合 (NVIDIA GPU)
pip install -r requirements-upscaler.txt
pip install -r requirements-footstep.txt

# テストエビデンスツールの依存
pip install -r tools/test-evidence/requirements.txt
python -m playwright install  # ブラウザバイナリ
```

### ツール起動

```bash
# GUIランチャー
python launcher.py

# 個別ツール (例)
python tools/chatbox-decorator/main.py --send "Hello" --frame sparkle
python tools/omikuji-bot/main.py
python tools/osc-timer/main.py countdown 5
python tools/texture-upscaler/upscale.py input.png
python tools/footstep-generator/generate.py --surfaces wood stone
python tools/thumbnail-generator/generate.py --title "ツール名" --theme purple

# テストエビデンス
python tools/test-evidence/evidence_runner.py spec.xlsx -c config.yaml
```

### テスト実行

テストは `tools/test-evidence/tests/` にのみ存在する (pytest)。

```bash
cd tools/test-evidence
pytest tests/
```

テストファイル:
- `test_gen_spec.py` — 自然言語→テストステップ変換のテスト
- `test_evidence_runner.py` — テスト実行エンジンのテスト
- `test_project_config.py` — YAML設定読み込みのテスト
- `test_record2spec.py` — 録画→仕様書変換のテスト
- `test_text2spec.py` — テキスト→Excel変換のテスト

**注意**: 他のツール (VRChat系、AI系) にはユニットテストがない。

### リンター・型チェック

プロジェクトにリンター・フォーマッター・型チェッカーの設定はない。
pyproject.tomlやsetup.cfgは存在しない (split-output内の分割パッケージにのみ生成)。

## コーディング規約

### 言語

- **コード内の変数名・関数名**: 英語 (`send_chatbox`, `resolve_device`)
- **コメント・docstring・エラーメッセージ・UIテキスト**: 日本語
- **ドキュメント (docs/, README)**: 日本語
- **コミットメッセージ**: 日本語ベース (例: `feat: 非技術者向けのユーザビリティ改善を実装`)

### エラーハンドリングパターン

`@friendly_error_handler` デコレータで main() をラップし、日本語でユーザーフレンドリーなエラーメッセージを表示する:

```python
from common.error_handler import friendly_error_handler

@friendly_error_handler("ツール名")
def main():
    ...
```

### インポートパターン (モノレポ内)

モノレポ内では `sys.path.insert` で共通モジュールを参照している:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.osc_client import create_client, send_chatbox
```

### CLI引数

全ツールが `argparse` を使用。複数モードがあるツールは `subparsers` を使う。

### GPU処理

`tools/common/gpu_utils.py` の `resolve_device()` でCUDA/ROCm自動検出。AMD GPUの場合は `fp32` に強制 (NaN回避):

```python
device, gpu_info = resolve_device("cuda")
if gpu_info["is_amd"]:
    # fp16ではなくfp32を使用
```

### 非同期処理

test-evidence の Playwright操作のみ `async/await` を使用。他のツールは同期処理。

### 型ヒント

Python 3.9+スタイル (`list[str]`, `dict[str, int]`) を関数シグネチャに使用。

## 依存関係

| パッケージグループ | ファイル | 主な依存 |
|---|---|---|
| 共通 | `requirements.txt` | python-osc>=1.8.0, Pillow>=10.0.0 |
| テクスチャ高画質化 | `requirements-upscaler.txt` | torch>=2.1.0, realesrgan>=0.3.0, opencv-python>=4.8.0 |
| 足音AI生成 | `requirements-footstep.txt` | torch>=2.1.0, torchaudio>=2.1.0, stable-audio-tools>=0.0.12 |
| テストエビデンス | `tools/test-evidence/requirements.txt` | playwright>=1.49, openpyxl>=3.1, pyyaml>=6.0 |

## ツール別の注意点

### VRChat系ツール (chatbox-decorator, omikuji-bot, osc-timer)
- VRChat OSCが有効 (`127.0.0.1:9000`) であることが前提
- Chatboxは144文字制限
- おみくじはSHA256ハッシュで日付ごとに結果を固定

### AI系ツール (texture-upscaler, footstep-generator)
- GPU推奨 (VRAM 8GB+)、CPUフォールバック可能
- モデルは初回実行時に自動ダウンロード (65MB〜3.5GB)
- AMD GPU使用時は自動でfp32に切り替え

### テストエビデンス (test-evidence)
- Excel入出力 (openpyxl)、YAML設定、Playwright自動操作
- `${variable}` 構文で設定ファイルの変数を展開
- 検証モード: screenshot, text, value, visible, hidden, url, db
- マッチング: 完全一致、`contains:部分文字列`、`regex:パターン`
- VBA Lite版 (無料) と Docker Pro版 (有料) のハイブリッド配布

### サムネイル生成 (thumbnail-generator)
- フォントパスがUnix系に固定 (IPA Gothic / WenQuanYi)
- 出力: 620x620px PNG

## Git運用

- ブランチ名: `claude/機能名-ランダムID` パターン
- コミットメッセージ: 日本語、prefixあり (feat:, docs:, fix: 等)
- `.gitignore`: `__pycache__/`, `*.pyc`, `.env`, `*.png` (サムネイル画像除外)

## 既知の技術的課題

- フォントパスがUnix系ハードコード (thumbnail-generator)
- `sys.path.insert` ハック (split_repos.shで解消予定)
- VRChat系・AI系ツールにユニットテストなし
- リンター/フォーマッター未設定
