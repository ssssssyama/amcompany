# CLAUDE.md

## Project Overview

VRChat向けニッチツール集。Python製のOSCユーティリティと、BOOTH出品用サムネイル生成ツールで構成。
100〜500円の衝動買い価格帯で、BOOTH（日本のインディーマーケットプレイス）にて販売予定。

## Repository Structure

```
amcompany/
├── docs/
│   └── product-ideas.md          # 商品企画書・ロードマップ
├── tools/
│   ├── common/                   # 共有ユーティリティ
│   │   ├── __init__.py
│   │   └── osc_client.py        # VRChat OSCプロトコルラッパー
│   ├── chatbox-decorator/        # チャットボックス装飾ツール
│   │   ├── README.md
│   │   └── main.py
│   ├── omikuji-bot/             # おみくじボット
│   │   ├── README.md
│   │   └── main.py
│   ├── osc-timer/               # タイマー・ストップウォッチ・ポモドーロ
│   │   ├── README.md
│   │   └── main.py
│   └── thumbnail-generator/     # BOOTHサムネイル画像生成
│       ├── README.md
│       └── generate.py
├── requirements.txt
└── .gitignore
```

## Tech Stack

- **Language**: Python 3.10+
- **Dependencies**: `python-osc>=1.8.0`, `Pillow>=10.0.0`
- **Protocol**: VRChat OSC (UDP, localhost:9000)
- **Package Manager**: pip

## Setup

```bash
pip install -r requirements.txt
```

VRChatでOSCを有効にする: Action Menu → Options → OSC → Enabled

## Running Tools

```bash
python tools/chatbox-decorator/main.py
python tools/omikuji-bot/main.py --seed "YourName"
python tools/osc-timer/main.py countdown 5
python tools/thumbnail-generator/generate.py --title "商品名" --theme purple --icon "✨"
```

各ツールは `--ip` と `--port` でOSC接続先を変更可能（デフォルト: 127.0.0.1:9000）。

## Code Conventions

- **命名規則**: snake_case（関数・変数）、UPPER_CASE（定数・辞書）
- **型ヒント**: 関数シグネチャに使用（例: `def decorate(text: str, frame: str = "sparkle") -> str`）
- **CLI**: 全ツールで argparse を使用
- **ドキュメント/コメント**: 日本語（VRChat日本コミュニティ向け）
- **モジュールdocstring**: ファイル先頭に記述
- **共有コード**: `tools/common/` に配置、各ツールから `sys.path` で参照
- **コミットメッセージ**: 日本語で簡潔に

## Architecture Patterns

- 各ツールは**スタンドアロン実行**（独立したCLIアプリ）
- 共有OSC機能は `tools/common/osc_client.py` に集約
- インタラクティブモード（ユーザー入力ループ + Ctrl+C終了）対応
- 非インタラクティブモード（バッチ/スクリプト）対応
- ノンブロッキング処理にはthreadingを使用

## Testing

現時点ではテストフレームワーク未導入。手動テストで確認。

## No CI/CD, No Linter

CI/CDパイプライン、リンター、フォーマッター未設定。PEP 8に準拠するコードスタイルを維持すること。

## Product Roadmap

`docs/product-ideas.md` に12商品の企画あり（実装済み3、未実装9）。新ツール追加時は同ドキュメントを参照。
