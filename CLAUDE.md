# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VRChat向けニッチツールのBOOTH販売プロジェクト + 24時間稼働の資産蓄積エージェントフレームワーク。日本語が主言語。

## Commands

### Asset Accumulation Agent (asset-accumulation-agent/)

```bash
# テスト実行（カレントディレクトリを asset-accumulation-agent/ に移動してから）
cd asset-accumulation-agent && python -m pytest tests/ -v

# 単一テストファイル
python -m pytest tests/test_catalog.py -v

# エージェント実行（デモモード: GPU不要）
python -m src --agent audio_pack --once

# 蓄積状況レポート
python -m src --stats
```

### VRChat Tools (tools/)

各ツールはスタンドアロンCLI。共通依存: `pip install -r requirements.txt`

```bash
python tools/chatbox-decorator/main.py --send "Hello" --frame sparkle
python tools/omikuji-bot/main.py --seed "username"
python tools/osc-timer/main.py countdown 5
python tools/footstep-generator/generate.py --surfaces wood stone  # GPU推奨
python tools/texture-upscaler/upscale.py ./textures/               # GPU推奨
python tools/thumbnail-generator/generate.py --all
```

GPU系ツールの追加依存: `pip install -r requirements-footstep.txt` / `pip install -r requirements-upscaler.txt`

## Architecture

### 二層構造

1. **`tools/`** — VRChat OSCツール群（スタンドアロンCLI）。`tools/common/osc_client.py` がOSC通信、`tools/common/gpu_utils.py` がGPU検出を共有。
2. **`asset-accumulation-agent/`** — エージェントフレームワーク。tools/のAI生成機能をラップし、24時間稼働で販売可能アセットを自動蓄積する。

### エージェントフレームワーク (asset-accumulation-agent/src/)

- **`agent.py`** — `BaseAgent`抽象基底クラス。新エージェントは`run()`と`estimate_value()`を実装する。`estimate_value()`でRunnerが実行優先度を決定。
- **`catalog.py`** — JSON Lines形式のアセット台帳。追記のみ設計でロック不要。`Asset`のステータスは `generated` → `quality_passed` → `packaged` → `listed` → `sold` と遷移。
- **`quality.py`** — 音声(RMS/再生時間)/画像(解像度)/テキスト(文字数)の品質ゲート。閾値未満のアセットを弾く。
- **`runner.py`** — `--once`/`--agent NAME`/`--daemon`/`--stats` の4モード。daemonモードでは`estimate_value()`降順で実行。
- **`agents/`** — `AGENT_REGISTRY`辞書に登録されたプラグイン式エージェント群。

### エージェントの換金性ティア

- **Tier S（直接売上）**: `audio_pack`（テーマ別足音パック）、`image_variants`（テクスチャパック）
- **間接**: `listing_writer`（商品説明の多言語自動生成）

### GPU対応

NVIDIA CUDA / AMD ROCm 6.1+ / CPUフォールバックの3段階。`gpu_utils.py`の`detect_gpu()`/`resolve_device()`で自動判定。AI系エージェントはGPUなし時デモモード（ダミーデータ生成）で動作。

## Key Conventions

- 設定は`config.yaml`（YAML）。テンプレートは`config.example.yaml`
- 生成物は`output/`配下に保存（.gitignore済み）、`catalog.jsonl`で追跡
- 商品企画・ロードマップは `docs/product-ideas.md` に集約（15商品計画）
- 価格帯: 100〜500円（BOOTH販売、インパルス購入狙い）
