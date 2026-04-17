# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ECサイトで安く仕入れ → 買取店に売却 → 利ざやを得る「せどり」利益商品自動抽出ツール。
Streamlit UI + CLI + Chrome拡張 + ローカルAPIサーバーの4つのインターフェースを持つ。

## Commands

```bash
pip install -r requirements.txt
playwright install              # Amazon/ヨドバシ等のスクレイピングに必要

# 統合ランチャー（価格サーバー + 自動利益抽出、デフォルトでカメラ/ゲーム/グラボ対象）
python run.py                              # サーバー + 自動抽出
python run.py --clear-cache                # キャッシュクリアして再検索
python run.py --categories all             # 全カテゴリ対象
python run.py --no-extract                 # 抽出なし（サーバーのみ）
python run.py --no-ui                      # Streamlit UIなし

# 自動抽出CLI単体（price_server.py 起動中が前提）
python auto_extract.py                                # デフォルト: カメラ/ゲーム/グラボ上位200件
python auto_extract.py --threshold 5000 --top 100     # 利益閾値・件数指定
python auto_extract.py --categories all               # 全カテゴリ
python auto_extract.py --no-scraper                   # API(楽天/Yahoo)のみ、高速
python auto_extract.py --clear-cache                  # キャッシュクリアして再検索
python auto_extract.py --crawl 100                    # Chrome拡張巡回モード（明示的）
python auto_extract.py --browse 20                    # Playwright巡回モード

# 利益分析
python analyze.py                           # 全分析
python analyze.py --category                # カテゴリ別利益率
python analyze.py --mercari                 # メルカリ相場比較
python analyze.py --shop-gap                # 買取店間価格差

# 価格サーバー単体
python price_server.py --port 8502
```

## Architecture

### データフロー

1. **入力**: `amcompany/all_data_*.csv`（cp932、11買取店のJAN・価格・カテゴリを列挙）
2. **csv_loader.py**: CSVを正規化し、各JAN×買取店の価格を集約。「利益候補スコア」を算出（= 買取価格 × 買取店数 / (最高値−2番目価格差+1)）
3. **ec_search.py**: 楽天API + Yahoo API + Playwrightスクレイパーを**2並列**でEC最安値を取得。APIレート制限はグローバルロックで1.5秒間隔を保証
4. **profit.py**: `現金利益 = 買取価格 - EC価格 - 送料`、ポイント込み利益・ROI・メルカリ販売利益・ポイント再投資ROIを計算
5. **analyze.py**: カテゴリ別分析、まとめ買いグルーピング、価格トレンド、メルカリ相場比較等
6. **出力**: `~/.kaitori-viewer/cache_results.json`（利益結果）、`~/.kaitori-viewer/ec_cache.json`（JAN単位EC検索キャッシュ）

### EC価格取得の三層構造

**APIレイヤー** (`ec_search.py`):
- 楽天市場API / Yahoo!ショッピングAPIでJAN検索
- 価格比率フィルタ（全ソース共通: EC価格が買取の25%以下→除外）・商品名スペック一致率チェック
- `_verify_worker.py`でAPI結果の商品ページを実際に訪問し、価格・在庫・除外条件を検証

**スクレイパーレイヤー** (`retailer_scraper.py` → `_*_worker.py`):
- Playwrightは全て**サブプロセス**として実行（Streamlitのイベントループとの競合回避）
- 有効ワーカー: `_amazon_worker.py`(Chromium), `_yodobashi_worker.py`(Firefox), `_kakaku_worker.py`(Chromium, 2段階方式), `_qoo10_worker.py`(Chromium)
- サーキットブレーカー（2回連続失敗で5分停止）を`retailer_scraper.py`に実装
- `stealth.py`でwebdriverフラグ除去等のbot対策を共有
- `_worker_common.py`で除外キーワード判定・価格抽出・アクセサリ判定を共有
- リテーラー同時検索数は最大3並列（`retailers.py`のThreadPoolExecutor）

**Chrome拡張レイヤー** (`chrome-extension/` + `price_server.py`):
- ビックカメラ、ジョーシン、ノジマ、ケーズデンキ、エディオン、コジマ、ソフマップの7サイトはPlaywright/CDP接続いずれでも100%ブロックされるため、Chrome拡張経由のみで対応
- CDPインフラ（`_cdp_browser.py`）は構築済みだが現状これらのサイトには効果なし。Brave/Chrome対応
- `auto_extract.py`がEC結果なしのJANを自動でChrome拡張の巡回キューに投入

### Chrome拡張 自動巡回フロー

1. `auto_extract.py` がAPI/スクレイパー検索後、EC結果なしのJANを `POST /crawl_queue` で `price_server.py` に投入
2. `background.js` が5秒間隔で `GET /crawl_queue` をポーリング
3. キューにJANがあれば自動で各サイトのタブを順番に開く（4秒間隔）
4. `content.js` が価格を抽出し `POST /add_price` で結果をサーバーに送信
5. 結果は `cache_results.json` に自動保存

`--crawl N` フラグで明示的に巡回モードを起動することも可能。`price_server.py` 未起動の場合はサイレントにスキップ。

### ポイント・キャンペーン計算

`campaign_calendar.py`が楽天・Yahoo!の当日キャンペーン（お買い物マラソン、スーパーSALE、5と0のつく日等）を判定し、ボーナスポイント率を自動算出。

### カテゴリフィルタ

`auto_extract.py` はデフォルトでカメラ・ゲーム・グラフィックボード関連に絞り込む。`--categories all` で全カテゴリ対象。

### 4つのインターフェース

| インターフェース | ファイル | 用途 |
|---|---|---|
| Streamlit UI | `app.py` | 対話的に検索・フィルタ・利益一覧表示 |
| CLI | `auto_extract.py` | バッチ自動抽出、Chrome拡張巡回連携 |
| APIサーバー | `price_server.py` | Chrome拡張からの価格受信 + 巡回キュー管理 |
| 統合ランチャー | `run.py` | 上記3つを1コマンドで起動（デフォルトで抽出ON） |

## Key Conventions

- CSVパス解決: `Path(__file__).resolve().parent.parent.parent`で`amcompany/`を指す（`app.py`, `auto_extract.py`, `analyze.py`, `price_server.py`の4箇所で同一パターン）
- CSVファイルは`all_data_YYYYMMDDHHMM.csv`をglob→降順ソートで最新を自動検出
- キャッシュ・ログは`~/.kaitori-viewer/`に保存（プロジェクトディレクトリ外）
- 11買取店の設定は`csv_loader.py`の`SHOP_CONFIGS`にハードコード（列番号マッピング）
- CDPブラウザはBrave優先（`_cdp_browser.py`）。実ブラウザプロファイルからCookieを同期
- 日本語が主言語（変数名・ログ・UI全て日本語）

## Known Issues

- **除外キーワードリストが複数箇所に分散**: `ec_search.py`（USED/EXCLUDED/ACCESSORY）、`_worker_common.py`（同）、`csv_loader.py`（EXCLUDED_CONDITIONS、別構造）。用途が異なるが更新時は要確認
- **Playwright並列実行がWindowsメモリ不足で失敗しやすい**: WinError 1455。WORKERS=2、リテーラー同時3並列に制限済み
- **`stock_checker.py`は未使用**: `check_stock_batch()`がどこからも呼ばれていない
- **7サイトがCDP/Playwright接続でもブロック**: Chrome拡張の自動巡回で対応
- **CDPワーカーは現状全サイトでブロックされる**: `_cdp_worker_common.py`の`run_worker()`で共通化済みだが、7サイト全てがCDP/Playwright接続を拒否するため実質Chrome拡張のみ有効

## Environment Variables (`.env`)

```
RAKUTEN_APP_ID
RAKUTEN_ACCESS_KEY
YAHOO_APP_ID
```
