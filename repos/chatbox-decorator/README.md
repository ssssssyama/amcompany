# VRC Chatbox デコレーター

VRChatのChatboxに送るテキストを装飾するツールです。

## 機能

- **フレーム装飾**: 10種類の装飾フレームでテキストを囲む
- **フォントスタイル変換**: アルファベットをBold/Italic/Monospace風に変換
- **タイピングアニメーション**: 1文字ずつ表示されるタイピング演出
- **対話モード**: リアルタイムにテキストを入力・装飾・送信

## 必要環境

- Python 3.10+
- VRChat（OSC有効化済み）

## セットアップ

```bash
pip install python-osc
```

VRChatの設定でOSCを有効にしてください:
Action Menu → Options → OSC → Enabled

## 使い方

### 対話モード（推奨）

```bash
python main.py
```

### 1回だけ送信

```bash
python main.py --send "こんにちは" --frame sparkle
```

### タイピング演出付き

```bash
python main.py --typing --frame heart
```

## 対話モードのコマンド

| コマンド | 説明 |
|---------|------|
| `/frame <名前>` | フレームを切り替え |
| `/style <名前>` | 文字スタイルを変更 (bold/italic/mono/none) |
| `/typing on/off` | タイピング演出のON/OFF |

## フレーム一覧

| 名前 | 表示例 |
|------|--------|
| sparkle | ✧˖°⌊ テキスト ⌉°˖✧ |
| star | ★·.·´¯`·.·★ テキスト ★·.·´¯`·.·★ |
| flower | ✿ テキスト ✿ |
| heart | ♡ テキスト ♡ |
| music | ♪♫ テキスト ♫♪ |
| arrow | 》 テキスト 《 |
| bracket | 【 テキスト 】 |
| wave | 〜 テキスト 〜 |
| diamond | ◆ テキスト ◆ |
| ribbon | ✦ テキスト ✦ |
