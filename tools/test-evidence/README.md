# test-evidence — テストエビデンス自動化ツール

テスト仕様書（Excel）を読み取り、ブラウザ操作を自動実行し、スクリーンショット＋検証結果をExcelにエビデンスとして貼り付けるツール。

## 機能

- **Excel仕様書読み取り**: テスト手順・期待値をExcelから自動取得
- **ブラウザ自動操作**: Playwrightで画面遷移・入力・クリック等を実行
- **スクリーンショット**: 各ステップの画面キャプチャを自動取得
- **画面検証**: テキスト・値・表示状態・URLの自動検証（OK/NG判定）
- **DB検証**: SQLクエリの結果が期待値と一致するか確認
- **エビデンス生成**: スクショ+OK/NG判定を元のExcelに自動貼付して出力

## セットアップ

```bash
pip install -r requirements.txt
playwright install chromium
```

## 使い方

### 1. テンプレート生成

```bash
python create_template.py
```

`examples/test_spec_template.xlsx` にサンプル付きテンプレートが生成されます。

### 2. テスト仕様書を記入

テンプレートに従って操作手順・検証内容を記入します。

| 列 | 内容 | 例 |
|---|---|---|
| 操作種別 | navigate / click / input / select / wait | `click` |
| 対象セレクタ | CSSセレクタ | `#login-button` |
| 入力値/期待値 | 操作に応じた値 | `testuser` |
| 検証種別 | screenshot / text / value / visible / url / db | `text` |
| 検証対象 | セレクタ or SQLクエリ | `.welcome-msg` |
| 期待値 | 検証の期待値 | `ようこそ` |

### 3. テスト実行

```bash
# 基本実行（ヘッドレス）
python evidence_runner.py テスト仕様書.xlsx

# ブラウザ表示して実行
python evidence_runner.py テスト仕様書.xlsx --headed

# 出力先を指定
python evidence_runner.py テスト仕様書.xlsx -o エビデンス.xlsx

# DB検証あり
python evidence_runner.py テスト仕様書.xlsx --db-url postgresql://user:pass@localhost/mydb
```

### 4. 結果確認

`テスト仕様書_evidence.xlsx` にエビデンスが自動生成されます:
- 各ステップのスクリーンショットがエビデンス列に貼付
- OK/NG判定が結果列に記入（色付き）
- 検証詳細が備考欄に追記

## 対応する操作種別

| 種別 | 動作 |
|---|---|
| `navigate` | 指定URLに遷移 |
| `click` | 要素をクリック |
| `input` | テキスト入力 |
| `select` | ドロップダウン選択 |
| `wait` | 指定ミリ秒待機 |

## 対応する検証種別

| 種別 | 動作 |
|---|---|
| `screenshot` | スクリーンショットのみ取得 |
| `text` | 要素のテキストが期待値と一致するか |
| `value` | 要素のvalue属性が期待値と一致するか |
| `visible` | 要素が表示されているか |
| `url` | URLが期待値と一致するか |
| `db` | SQLクエリ結果が期待値と一致するか |
