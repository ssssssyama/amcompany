# TestEvidence VBA Lite — セットアップ手順

## 必要なもの

- **Windows 10/11**
- **Microsoft Excel**（マクロ有効）
- **Microsoft Edge**（Windows標準搭載）
- **Selenium Basic**（無料）

## 手順

### 1. Selenium Basic のインストール

1. [Selenium Basic](https://github.com/nicolestandifer3/SeleniumBasic-VBA/releases) からインストーラをダウンロード
2. `SeleniumBasic-x.x.x.exe` を実行してインストール

### 2. Edge WebDriver の配置

1. Edge のバージョンを確認: `edge://version/` にアクセス
2. 対応バージョンの [Edge WebDriver](https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/) をダウンロード
3. `msedgedriver.exe` を Selenium Basic のインストール先にコピー
   - 通常: `C:\Users\<ユーザー名>\AppData\Local\SeleniumBasic\`

### 3. VBA コードのインポート

1. テスト仕様書Excelを開く（Pro版のテンプレートと同じフォーマット）
2. `Alt + F11` で VBE（Visual Basic Editor）を開く
3. メニュー「ツール」→「参照設定」→「Selenium Type Library」にチェック
4. メニュー「ファイル」→「ファイルのインポート」→ `TestEvidence.bas` を選択
5. `Ctrl + S` で保存（ファイル形式を `.xlsm` に変更）

### 4. テスト実行

1. テスト仕様書に操作手順を記入（Pro版と同じフォーマット）
2. `Alt + F8` → `RunTestEvidence` を選択 → 「実行」

## テスト仕様書のフォーマット

7行目からデータを記入（Pro版のテンプレートと同じ列配置）:

| 列 | 内容 | 例 |
|---|---|---|
| A | No. | 1 |
| B | テスト項目 | ログインページを開く |
| C | 操作種別 | navigate |
| D | 対象セレクタ | #login-button |
| E | 入力値 | https://example.com/login |
| F | 検証種別 | text |
| G | 検証対象 | .welcome-msg |
| H | 期待値 | ようこそ |
| I | 結果 | (自動入力) |
| J | エビデンス | (自動貼付) |
| K | 備考 | (自動入力) |

## 対応操作

| 操作 | 説明 |
|---|---|
| navigate | URLに遷移 |
| click | 要素をクリック |
| input | テキスト入力 |
| select | ドロップダウン選択 |
| wait | 指定ミリ秒待機 |

## 対応検証

| 検証 | 説明 |
|---|---|
| screenshot | スクリーンショットのみ |
| text | テキスト完全一致 |
| visible | 要素が表示されているか |

## Pro版との比較

| 機能 | Lite版 | Pro版 (Docker) |
|---|---|---|
| 操作種別 | 5種 | 13種 |
| 検証種別 | 3種 | 7種 + 部分一致/正規表現 |
| DB検証 | - | A5M2連携 |
| 複数シート一括 | - | 対応 |
| NG時制御 | - | abort/continue |
| Excel列カスタマイズ | - | YAML設定で自由に変更 |
| 変数置換 (${変数名}) | - | 対応 |
| 認証自動化 | - | form/basic/cookie |
| 環境切替 | - | 設定ファイルで切替 |
| インストール | Selenium Basic のみ | Docker |
| 配布方法 | Excelファイル配布 | Dockerイメージ |

Pro版の詳細は [Docker版 README](../docker/) を参照してください。
