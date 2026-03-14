# BOOTH用サムネイル自動生成ツール

BOOTH出品用の620x620pxサムネイル画像をPythonで自動生成するツールです。

## 機能

- **グラデーション背景**: 対角線方向のグラデーション
- **装飾要素**: 半透明の円、角の装飾線
- **8種類のカラーテーマ**: purple, blue, green, red, pink, orange, dark, gold
- **日本語対応**: IPAゴシックフォントを使用
- **一括生成**: 全商品のサムネイルをまとめて生成

## 必要環境

- Python 3.10+
- Pillow

## セットアップ

```bash
pip install Pillow
```

## 使い方

### 単体生成

```bash
python generate.py --title "商品名" --subtitle "キャッチコピー" --theme purple --icon "✨"
```

### 全商品一括生成

```bash
python generate.py --all
```

### オプション一覧

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--title` | 商品タイトル | (必須) |
| `--subtitle` | サブタイトル | 空 |
| `--theme` | カラーテーマ | purple |
| `--icon` | アイコン絵文字 | 🎮 |
| `--brand` | ブランド名 | VRC Tools |
| `--output` | 出力ファイル名 | thumbnail.png |
| `--all` | 全商品を一括生成 | - |

## カラーテーマ

| テーマ | 用途例 |
|--------|--------|
| purple | デコレーター系 |
| blue | ユーティリティ系 |
| green | ツール系 |
| red | ゲーム系 |
| pink | かわいい系 |
| orange | 季節系 |
| dark | ホラー/クール系 |
| gold | おみくじ/イベント系 |
