# プログラムに詳しくない人がこのツール群を使う際の障壁まとめ

## 対象

VRChat向けPythonツール群（Chatboxデコレーター、おみくじBot、タイマー、足音AI生成、テクスチャ高画質化、サムネイル生成）と、テストエビデンス自動化ツール（test-evidence）。

BOOTH等で購入するVRChatユーザーや、SI現場でtest-evidenceを使う担当者を想定。

---

## 障壁一覧

### 1. Python環境の構築（全ツール共通）

- Python自体のインストール（バージョン指定、PATHの設定）が最初の大きなハードル
- `pip install` コマンドの実行に不慣れ
- 仮想環境（venv）の概念がなく、グローバルインストールで環境破壊のリスク
- ツールごとに `requirements.txt` が分かれており（`requirements.txt`、`requirements-footstep.txt`、`requirements-upscaler.txt`）、どれを入れるべきか迷う

### 2. コマンドライン操作への不慣れ（全ツール共通）

- ターミナル/コマンドプロンプトの開き方自体がわからない
- `python main.py --send "こんにちは" --frame sparkle` のような引数の書き方が直感的でない
- カレントディレクトリの概念（`cd` で移動する必要性）がわからない
- ファイルパスの指定方法（相対パス vs 絶対パス）が不明

### 3. GUIが一切ない（全ツール共通）

- 全ツールがCLIのみで、グラフィカルな操作画面がない
- VRChatユーザーはUnity等のGUI操作に慣れているため、CLIとのギャップが大きい
- 設定変更もコマンド引数やYAMLファイルの手編集が必要

### 4. GPU環境・ドライバの設定（AI系ツール）

- NVIDIA CUDA / AMD ROCm のインストールと設定が非常に複雑
- VRAM要件（8GB以上推奨）を満たすGPUがあるか自分で判断できない
- WSL2経由でのAMD GPU利用は上級者でも手間がかかる
- `HSA_OVERRIDE_GFX_VERSION=11.0.0` のような環境変数設定が意味不明
- **該当ツール**: `footstep-generator`、`texture-upscaler`

### 5. モデルのダウンロードとライセンス（AI系ツール）

- Hugging Faceアカウントの作成やトークン設定が必要な場合がある
- 初回ダウンロードに時間がかかり（モデル約3.5GB）、途中で止まったように見える
- Stable Audio Openのライセンス条件（年商$1M未満は無料等）の理解が必要
- **該当ツール**: `footstep-generator`、`texture-upscaler`

### 6. VRChat OSC設定（VRC系ツール）

- VRChat側でOSCを有効化する手順（Action Menu → Options → OSC → Enabled）を知らない
- OSC（Open Sound Control）が何なのか理解がない
- 動作確認の方法がわからない（送信できているのか見えない）
- **該当ツール**: `chatbox-decorator`、`omikuji-bot`、`osc-timer`

### 7. test-evidence特有の障壁

- **CSSセレクタ**: `#login-button`、`.welcome-msg` の書き方がわからない
- **YAML設定ファイル**: インデント間違いでエラーになりやすく、原因が特定しにくい
- **Playwrightの追加インストール**: `playwright install chromium` という追加手順が必要
- **Docker操作**: Pro版はDocker Composeの知識が前提
- **A5M2接続文字列**: DB検証の設定が複雑
- **Excelフォーマットの列マッピング**: 設定ミスしやすく、エラーメッセージが不親切

### 8. エラー発生時の対処（全ツール共通）

- Pythonのトレースバックが英語かつ長く、どこが問題か読み取れない
- 依存パッケージのバージョン不整合の解決方法がわからない
- ネットワーク関連エラー（OSC送信失敗、モデルダウンロード失敗）の切り分けが難しい

### 9. ドキュメントの導線不足

- トップレベルにREADMEがなく、各ツールのREADMEにたどり着きにくい
- ドキュメントが開発者目線で書かれており「まず何をすればいいか」が不明
- BOOTHで購入した人がGitHubリポジトリの構造を理解できるか疑問
- クイックスタートガイドや画像付きセットアップ手順がない

---

## 改善の方向性

| 障壁 | 改善案 |
|------|--------|
| Python環境構築 | PyInstaller等でexe化 / Docker化 / ワンクリックインストーラー |
| CLI操作 | 簡易GUI追加（Tkinter/Gradio）、またはダブルクリックで起動できるバッチファイル（.bat）の提供 |
| GPU設定 | CPUフォールバックの明示、GPUなしでも動く旨の記載強化 |
| OSC設定 | 画像付きセットアップガイドの同梱 |
| エラー対処 | 日本語エラーメッセージ、FAQ、よくあるエラーと対処法のドキュメント |
| 導線不足 | トップレベルREADME作成、ツール一覧と概要ページの整備 |
| test-evidence | CSSセレクタの入門ガイド、YAML設定のバリデーション強化とわかりやすいエラーメッセージ |
