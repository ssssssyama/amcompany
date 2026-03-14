# OSCタイマー＆ストップウォッチ

VRChatのChatboxにタイマーやストップウォッチを表示するツールです。

## 機能

- **カウントダウン**: 指定時間からカウントダウン（プログレスバー付き）
- **ストップウォッチ**: 経過時間を計測
- **ポモドーロ**: 作業25分→休憩5分のサイクルを繰り返す
- **アバターパラメータ連携**: 進捗をFloat値で送信可能

## 必要環境

- Python 3.10+
- VRChat（OSC有効化済み）

## セットアップ

```bash
pip install python-osc
```

## 使い方

### カウントダウン

```bash
# 5分カウントダウン
python main.py countdown 5

# ラベル付き
python main.py countdown 3 --label "ゲーム開始まで"
```

### ストップウォッチ

```bash
python main.py stopwatch
# Ctrl+C で停止
```

### ポモドーロ

```bash
# デフォルト（25分作業 / 5分休憩 × 4サイクル）
python main.py pomodoro

# カスタム設定
python main.py pomodoro --work 50 --break 10 --cycles 2
```

## 表示例

```
⏱️ 残り 04:32 [████████░░]
☕ 休憩中 [2/4] 03:15
🍅 作業中 [1/4] 24:50 [█░░░░░░░░░]
```

## アバターパラメータ連携

`--param` オプションで進捗値（0.0〜1.0）をアバターパラメータに送信できます。

```bash
python main.py countdown 5 --param "TimerProgress"
```

これにより、タイマーの進捗に応じてアバターの表情やエフェクトを変化させることができます。
