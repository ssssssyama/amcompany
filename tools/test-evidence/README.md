# test-evidence — テストエビデンス自動化ツール

テスト仕様書（Excel）を読み取り、ブラウザ操作を自動実行し、スクリーンショット＋検証結果をExcelにエビデンスとして貼り付けるツール。

## エディション

| | Lite版（VBA） | Pro版（Docker） |
|---|---|---|
| **価格** | 無料 | 導入支援費 + 年間保守 |
| **操作種別** | 5種 | 13種（全対応） |
| **検証種別** | 3種 | 7種 + 部分一致/正規表現 |
| **DB検証** | - | A5M2連携 |
| **複数シート** | - | 対応 |
| **NG時制御** | - | abort/continue |
| **Excel列カスタマイズ** | - | YAML設定で自由に変更 |
| **変数置換** | - | `${変数名}` 対応 |
| **認証自動化** | - | form/basic/cookie |
| **インストール** | Selenium Basic のみ | Docker |
| **配布** | Excelファイル | Dockerイメージ |

- **Lite版**: [vba-lite/](vba-lite/) — Excelマクロだけで動作。現場への持ち込みが容易
- **Pro版**: [docker/](docker/) — 全機能対応。顧客環境のDockerにデプロイ

## 機能（Pro版）

- **Excel仕様書読み取り**: テスト手順・期待値をExcelから自動取得（フォーマット可変対応）
- **ブラウザ自動操作**: Playwrightで画面遷移・入力・クリック等を実行（13種の操作に対応）
- **スクリーンショット**: 各ステップの画面キャプチャを自動取得
- **画面検証**: テキスト・値・表示状態・URLの自動検証（完全一致/部分一致/正規表現）
- **DB検証（A5M2連携）**: A5:SQL Mk-2 経由でSQLクエリを実行し、結果が期待値と一致するか確認
- **エビデンス生成**: スクショ+OK/NG判定を元のExcelに自動貼付して出力
- **プロジェクト設定**: YAML設定ファイルで環境差分・認証・Excelフォーマットを制御
- **複数シート対応**: 1ファイル内の複数シートを一括実行可能
- **NG時制御**: NG発生時に中断/継続を選択可能
- **ログ出力**: コンソール＋ファイルに実行ログを記録

## セットアップ

### Pro版（Docker）

```bash
cd docker
docker compose build
# テスト仕様書と設定ファイルを docker/work/ に配置
docker compose run test-evidence テスト仕様書.xlsx -c config.yaml
```

### Pro版（直接実行）

```bash
pip install -r requirements.txt
playwright install chromium
```

### Lite版（VBA）

[vba-lite/setup.md](vba-lite/setup.md) を参照。

## 使い方

### 1. テンプレート生成

```bash
python create_template.py
```

`examples/test_spec_template.xlsx` にサンプル付きテンプレートが生成されます。

### 2. プロジェクト設定ファイルを作成

プロジェクトごとにYAML設定ファイルを作成し、環境情報・認証・ブラウザ設定を定義します。

```bash
cp examples/project_config.yaml my_project.yaml
```

設定ファイルで定義した変数は、Excel仕様書内で `${変数名}` として参照できます。

```yaml
environment:
  base_url: "https://staging.example.com"
  variables:
    admin_user: "admin@example.com"
    admin_pass: "P@ssw0rd123"
```

例えば仕様書のURL列に `${base_url}/login` と書けば、実行時に `https://staging.example.com/login` に自動置換されます。環境ごとに設定ファイルを切り替えるだけで、同じ仕様書を使い回せます。

### 3. テスト仕様書を記入

テンプレートに従って操作手順・検証内容を記入します。

| 列 | 内容 | 例 |
|---|---|---|
| 操作種別 | navigate / click / input / wait_for 等 | `click` |
| 対象セレクタ | CSSセレクタ | `#login-button` |
| 入力値/期待値 | 操作に応じた値（`${変数名}` 使用可） | `${test_user}` |
| 検証種別 | screenshot / text / value / visible / hidden / url / db | `text` |
| 検証対象 | セレクタ or SQLクエリ（`${変数名}` 使用可） | `.welcome-msg` |
| 期待値 | 検証の期待値（`${変数名}` 使用可） | `ようこそ` |

### 4. テスト実行

```bash
# 設定ファイルを指定して実行（推奨）
python evidence_runner.py テスト仕様書.xlsx -c my_project.yaml

# ブラウザ表示して実行
python evidence_runner.py テスト仕様書.xlsx -c my_project.yaml --headed

# 出力先を指定
python evidence_runner.py テスト仕様書.xlsx -c my_project.yaml -o エビデンス.xlsx

# 特定シートだけ実行
python evidence_runner.py テスト仕様書.xlsx -c my_project.yaml --sheets ログイン機能 商品検索

# 設定ファイルなしでも実行可能（従来通り）
python evidence_runner.py テスト仕様書.xlsx

# CLI引数でA5M2設定を上書き（設定ファイルより優先）
python evidence_runner.py テスト仕様書.xlsx -c my_project.yaml \
  --a5m2-cmd "C:\A5M2\A5M2cmd.exe" \
  --a5m2-connect "接続文字列"
```

### 5. 結果確認

`テスト仕様書_evidence.xlsx` にエビデンスが自動生成されます:
- 各ステップのスクリーンショットがエビデンス列に貼付
- OK/NG判定が結果列に記入（色付き）
- 検証詳細が備考欄に追記
- 実行ログが `テスト仕様書_evidence.log` に保存

## プロジェクト設定ファイル

YAML形式の設定ファイルで、各社プロダクト固有の設定を管理します。サンプル: `examples/project_config.yaml`

### 設定項目

| セクション | 項目 | 説明 |
|---|---|---|
| `environment.base_url` | ベースURL | `${base_url}` で参照可能 |
| `environment.variables` | カスタム変数 | `${変数名}` で仕様書内から参照 |
| `auth.type` | 認証方式 | `none` / `basic` / `form` / `cookie` |
| `browser.viewport` | ビューポートサイズ | width / height |
| `browser.timeout` | 操作タイムアウト（ms） | デフォルト: 30000 |
| `browser.ignore_https_errors` | 証明書エラー無視 | 自己署名証明書の環境用 |
| `excel.columns` | 列マッピング | 顧客のExcelフォーマットに対応 |
| `excel.data_start_row` | データ開始行 | デフォルト: 7 |
| `excel.sheets` | 実行対象シート | 省略時は全シート（凡例除く） |
| `excel.date_cell` | テスト日セル | デフォルト: B3 |
| `test.on_fail` | NG時動作 | `continue`（続行）/ `abort`（中断） |
| `a5m2.cmd` | A5M2cmd.exe パス | DB検証用 |
| `a5m2.connect` | A5M2接続文字列 | DB検証用 |

### Excelフォーマットの可変対応

顧客のExcelフォーマットが標準と異なる場合、設定ファイルで列マッピングを変更できます:

```yaml
excel:
  data_start_row: 10    # データが10行目から始まる場合
  date_cell: "C2"       # テスト日のセル位置
  sheets:               # 実行対象シート
    - "ログイン機能"
    - "商品検索"
  columns:              # 変更したい列だけ指定
    no: "B"             # No.がB列にある場合
    action: "D"         # 操作種別がD列にある場合
    result: "L"         # 結果がL列にある場合
```

### 認証方式

**フォーム認証**（ログインフォームに自動入力）:
```yaml
auth:
  type: form
  login_url: "${base_url}/login"
  fields:
    - selector: "#username"
      value: "${admin_user}"
    - selector: "#password"
      value: "${admin_pass}"
  submit_selector: "#login-button"
```

**Basic認証**:
```yaml
auth:
  type: basic
  username: "admin"
  password: "secret"
```

**Cookie認証**（事前定義のCookieを設定）:
```yaml
auth:
  type: cookie
  cookies:
    - name: "session_id"
      value: "abc123"
      domain: ".example.com"
      path: "/"
```

### NG時の制御

```yaml
test:
  on_fail: abort  # NG発生時、当該シートの残りステップをSKIPにする
```

- `continue`（デフォルト）: NGでも後続ステップを実行し続ける
- `abort`: NG発生時点で残りステップをSKIPにする（ログイン失敗時など、後続が無意味な場合に有効）

### 環境の切り替え

同じ仕様書を複数環境で使い回す場合、設定ファイルを環境ごとに作成します:

```
config/
  dev.yaml        # 開発環境
  staging.yaml    # ステージング環境
  production.yaml # 本番環境（読み取り専用テスト用）
```

```bash
# 開発環境でテスト
python evidence_runner.py テスト仕様書.xlsx -c config/dev.yaml

# ステージング環境でテスト
python evidence_runner.py テスト仕様書.xlsx -c config/staging.yaml
```

## 対応する操作種別

| 種別 | 動作 | セレクタ | 入力値 |
|---|---|---|---|
| `navigate` | 指定URLに遷移 | - | URL |
| `click` | 要素をクリック | CSS | - |
| `input` | テキスト入力 | CSS | テキスト |
| `select` | ドロップダウン選択 | CSS | 値 |
| `wait` | 固定秒数待機 | - | ミリ秒 |
| `wait_for` | 要素が表示されるまで待機 | CSS | タイムアウト(ms) |
| `upload` | ファイルアップロード | CSS (`input[type=file]`) | ファイルパス |
| `hover` | マウスオーバー | CSS | - |
| `scroll` | スクロール | CSS（要素まで） or なし | ピクセル数 |
| `keyboard` | キー入力 | - | `Enter`, `Tab`, `Escape` 等 |
| `alert_accept` | ダイアログを承認 | - | - |
| `alert_dismiss` | ダイアログをキャンセル | - | - |
| `iframe` | iframeにフォーカス切替 | CSS | - |

## 対応する検証種別

| 種別 | 動作 |
|---|---|
| `screenshot` | スクリーンショットのみ取得 |
| `text` | 要素のテキストが期待値と一致するか |
| `value` | 要素のvalue属性が期待値と一致するか |
| `visible` | 要素が表示されているか |
| `hidden` | 要素が非表示/不在であるか |
| `url` | URLが期待値と一致するか |
| `db` | A5M2cmd経由でSQLクエリを実行し、結果が期待値と一致するか |

### 期待値の記法

text, value, url, db 検証で使用可能:

| 記法 | 照合方式 | 例 |
|---|---|---|
| そのまま記述 | 完全一致（デフォルト） | `ようこそ、testuser さん` |
| `contains:文字列` | 部分一致 | `contains:ようこそ` |
| `regex:パターン` | 正規表現 | `regex:注文番号:\d+` |

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

## exe 版ビルド（Python 環境不要で配布）

PyInstaller を使い、Python 環境がないマシンでも実行できる exe ファイルを生成できます。

### ビルド手順

**Windows（推奨）:**

```bat
cd tools\test-evidence
build_exe.bat
```

**手動:**

```bash
cd tools/test-evidence
pip install pyinstaller
python build_exe.py
```

### 出力

`dist/test-evidence/` に以下が生成されます:

| フォルダ | 内容 |
|---------|------|
| `evidence-runner/` | テスト実行エンジン（メインツール） |
| `gen-spec/` | テスト定義 → Excel 変換 |
| `record2spec/` | Playwright 録画 → YAML 変換 |
| `text2spec/` | プレーンテキスト → YAML/Excel 変換 |
| `create-template/` | Excel テンプレート生成 |
| `examples/` | サンプルファイル |
| `install-browsers.bat/.sh` | Chromium ブラウザインストーラ |

### exe 版の利用者向けセットアップ

テスト実行（evidence-runner）には Chromium ブラウザが必要です。
初回のみ以下を実行してください:

```bat
:: Windows
install-browsers.bat

:: macOS/Linux
./install-browsers.sh
```

### exe 版の使用例

```bat
:: テスト実行
evidence-runner\evidence-runner.exe spec.xlsx -c config.yaml -o output.xlsx --headed

:: テスト定義からExcel生成
gen-spec\gen-spec.exe test_spec.yaml -o spec.xlsx

:: Playwright録画からYAML変換
record2spec\record2spec.exe recorded.py -o test_spec.yaml
```
