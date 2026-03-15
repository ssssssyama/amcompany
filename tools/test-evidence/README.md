# test-evidence — テストエビデンス自動化ツール

テスト仕様書（Excel）を読み取り、ブラウザ操作を自動実行し、スクリーンショット＋検証結果をExcelにエビデンスとして貼り付けるツール。

## 機能

- **Excel仕様書読み取り**: テスト手順・期待値をExcelから自動取得
- **ブラウザ自動操作**: Playwrightで画面遷移・入力・クリック等を実行
- **スクリーンショット**: 各ステップの画面キャプチャを自動取得
- **画面検証**: テキスト・値・表示状態・URLの自動検証（OK/NG判定）
- **DB検証（A5M2連携）**: A5:SQL Mk-2 経由でSQLクエリを実行し、結果が期待値と一致するか確認
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

# DB検証あり（A5M2連携）
python evidence_runner.py テスト仕様書.xlsx \
  --a5m2-cmd "C:\A5M2\A5M2cmd.exe" \
  --a5m2-connect "__ConnectionType=Internal;ProviderName=MySQL;UserName=user;Password=pass;ServerName=localhost;Port=3306;Database=mydb"
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
| `db` | A5M2cmd経由でSQLクエリを実行し、結果が期待値と一致するか |

## DB検証（A5M2連携）

DB検証には [A5:SQL Mk-2](https://a5m2.mmatsubara.com/) のコマンドラインユーティリティ（A5M2cmd）を使用します。

### 前提条件

- A5:SQL Mk-2 がインストール済みであること
- A5M2cmd.exe にパスが通っている、またはフルパスを指定すること

### 接続文字列の例

```
# MySQL
__ConnectionType=Internal;ProviderName=MySQL;UserName=user;Password=pass;ServerName=localhost;Port=3306;Database=mydb

# PostgreSQL
__ConnectionType=Internal;ProviderName=PostgreSQL;UserName=user;Password=pass;ServerName=localhost;Port=5432;Database=mydb

# SQL Server
__ConnectionType=Internal;ProviderName=MSSQL;UserName=user;Password=pass;ServerName=localhost;Database=mydb
```

### 動作の仕組み

1. テスト仕様書の「検証対象」列に書かれたSQLを一時ファイルに書き出し
2. `A5M2cmd.exe /Connect=... /RunSQL /FileName=...` で実行
3. 出力されたCSV（Query-1.csv）を読み取り
4. 1行目の1列目の値を「期待値」列と照合してOK/NG判定
