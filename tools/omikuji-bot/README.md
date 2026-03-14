# 今日の運勢おみくじBot

VRChatのChatboxに今日の運勢を表示するツールです。

## 機能

- **日替わりおみくじ**: 大吉〜大凶の7段階（同じ日は同じ結果）
- **ラッキーアイテム & カラー**: 毎日変わるおすすめアイテムと色
- **アドバイス**: VRChat向けの一言アドバイス
- **アバターパラメータ連携**: 運勢に応じてFloat値（0.0〜1.0）をパラメータに送信

## 必要環境

- Python 3.10+
- VRChat（OSC有効化済み）

## セットアップ

```bash
pip install python-osc
```

## 使い方

### 基本（Chatboxに運勢を表示）

```bash
python main.py
```

### 名前でシードを固定（フレンドと結果を比較できる）

```bash
python main.py --seed "あなたの名前"
```

### OSC送信せずに結果だけ確認

```bash
python main.py --dry-run
```

## アバターパラメータ連携

デフォルトで `LuckScore` というFloat型パラメータ（0.0〜1.0）が送信されます。
アバターのAnimator Controllerでこの値に応じた演出を設定できます。

- 1.0 = 大吉（例: 金色のオーラ）
- 0.5 = 中吉（例: 通常状態）
- 0.0 = 大凶（例: 暗いオーラ）

パラメータ名を変更:
```bash
python main.py --param "MyLuckParam"
```

パラメータ送信を無効化:
```bash
python main.py --no-param
```
