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
- 有効ワーカー（買取店向け新品）:
  - `_amazon_worker.py`(Chromium), `_yodobashi_worker.py`(Firefox), `_kakaku_worker.py`(Chromium, 2段階方式), `_qoo10_worker.py`(Chromium)
  - `_tsukumo_worker.py`(Chromium, JAN直URL `/goods/{JAN}/` 方式、URL自体がJAN保証、実機検証済み)
- **一時無効化中**: `_dospara_worker.py` / `_pc_koubou_worker.py` / `_mapcamera_worker.py` / `_kitamura_worker.py` — 誤検出リスクあり。ファイルと関数定義は残置、復活時は実HTML調査 + 価格妥当性チェック追加が必須

**5サイトの実機検証結果と対応状況**:
- **ツクモ** ✅ **有効**: JAN直URL `/goods/{JAN}/` でJANが一意に商品を指す。存在しないJANはトップにリダイレクト→`null`。実機テスト: RTX5090 正しく取得、ポケカカートン `null`（誤検出なし）
- **ドスパラ** 🔒 **保留**: 商品名検索+rapidfuzz類似度60%では不足。実機確認で「RTX5090」検索 → RTX5090搭載GALLERIA PC本体（130万円）がヒット、CSV側のGPU単体（13万円）と**価格桁違い誤マッチ**のリスクあり。価格妥当性チェック追加が必須
- **パソコン工房** 🔒 **保留**: JS遅延描画で body 文字列に価格が出ない（bot検知疑い）
- **マップカメラ** 🔒 **保留**: Chromium HTTP2 エラー、Firefox動作するがDNS解決不安定
- **キタムラ** 🔒 **保留**: 完全SPAで `body.textContent` に価格なし
- サーキットブレーカー（2回連続失敗で5分停止）を`retailer_scraper.py`に実装
- `stealth.py`でwebdriverフラグ除去等のbot対策を共有
- `_worker_common.py`で除外キーワード判定・価格抽出・アクセサリ判定を共有
- リテーラー同時検索数は最大3並列（`retailers.py`のThreadPoolExecutor）

**買取店向け（新品EC）の仕入先**:
- API: 楽天市場（新形式認証）、Yahoo!ショッピング
- Playwrightスクレイパー: Amazon、ヨドバシ、価格.com、Qoo10（ツクモ・ドスパラ・パソコン工房・マップカメラ・キタムラ は精度未検証のため一時無効化）
- Chrome拡張巡回: ビックカメラ、ジョーシン、ノジマ、ケーズデンキ、エディオン、コジマ、auPAYマーケット、**セブンネット**、**フジヤカメラ**、**楽天ブックス**

Chrome拡張による巡回は実ブラウザで動作するため bot検知を回避できる。直接スクレイピング（Playwright）では bot検知や JS遅延描画で取得困難なサイトも、実ブラウザの通常閲覧と同等の振る舞いで動作する。

**メルカリ転売向け（中古EC）の仕入先 — 別系統**:
- **ハードオフネットモール** (`_hardoff_worker.py`, `netmall.hardoff.co.jp/search/?keyword={JAN}`)
  - 商品ごとに在庫1個（ユニーク）、無在庫転売向けの低リスク仕入先
  - **重要**: 買取店は基本「新品買取」のため、ハードオフ仕入は買取店利益判定には使わない
  - `mercari_resale_finder.py` で「ハードオフ仕入 → メルカリ販売」の転売利益を計算
  - `--mode mercari-resale` で独立モードとして実行
  - JANマッチ判定: 検索ヒット0件でも新着30件を表示する仕様のため、商品カードに JAN が含まれるカードのみ採用（精度優先）

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

### 検索対象選定モード（--mode）

利益商品発見の14戦略を統合。`--mode hybrid`（デフォルト）で全ソース統合。hybrid モードでの優先順位:

1. **戦略E (kaitori-up)**: `kaitori_upward_detector.py` — `~/.kaitori-viewer/kaitori_snapshots/` に毎回CSV要約を保存し、最新2スナップショットを比較して買取価格が5%以上上昇したJAN（買取店値上げ＝需要急増の先行指標）。`all_data_*.csv` から自動ブートストラップ可能
2. **戦略P (price-anomaly)**: `price_anomaly_detector.py` — `price_history.json` から現在価格が過去30日中央値の40%以下のJAN（値付けミス・出血価格の即買い候補）
3. **戦略I (new-release)**: `new_release_finder.py` — 楽天/Yahoo APIで発売日直近30日以内の新商品JAN。`ec_search.py` の楽天エントリに `release_date` 追加済み
4. **戦略B (sale)**: `sale_finder.py` — 楽天/Yahooランキング ∩ CSV
5. **戦略C (price-drop)**: `price_drop_detector.py` — `price_history.json` から10%以上下落
6. **戦略G (restock)**: `restock_monitor.py` — `cache_results.json` の過去利益JANで現在「在庫なし/残りわずか」
7. **戦略O (kaitori-disappear)**: `kaitori_upward_detector.detect_kaitori_disappearances()` — 過去3店舗以上扱っていたが現在全店舗で扱わなくなったJAN（買取停止＝需要爆発の疑い）
8. **戦略T (discontinued)**: `csv_loader.is_discontinued()` — 商品名に「生産終了」「廃番」等のマーカーを含むJAN（希少化シグナル）。`EXCLUDED_CONDITIONS` を `_BAD_CONDITIONS`（除外）と `_DISCONTINUED_MARKERS`（優先）に分離済み
9. **戦略M (mercari-density)**: `mercari_density_detector.py` — `mercari_history.json` からメルカリ出品数が過去平均の1.5倍以上に急増したJAN（転売業者動き出しシグナル）。事前に `python mercari_scraper.py --top N` で履歴蓄積必要
10. **戦略A+D**: `csv_loader.py` の新スコア式
    - スコア = 買取価格 × (最高値−2番目の差) × 店舗数 × 履歴ボーナス / 1000
    - 戦略D: 店舗間価格差が大きい = 情報の非対称性 = 狙い目
    - 戦略A: 過去に利益が出たJANは1.5倍ブースト
11. **戦略H (point-spike)**: `ec_search.py` で楽天 `pointRate` をAPIから取得。`ec_cache.json` から `point_rate ≥ 10` のJANを抽出してスコア1.5倍ブースト（A+Dに自動適用）
12. **戦略Z (pattern-learning)**: `success_pattern_scorer.py` — `cache_results.json` の過去利益商品からカテゴリ/価格帯/キーワード頻度を統計抽出し、新JANを類似度スコア(0.5〜2.0)で再計算（A+Dに乗算適用）
13. **戦略F (cross-mall)**: `mall_arbitrage.py` — 楽天とYahooで同一JANの価格差2000円以上の商品をレポート出力（独立モード、検索フローには組み込まない）

実行例:
- `--mode hybrid` 全ソース統合（デフォルト、戦略 E+P+I+B+C+G+O+T+M+A+D+H+Z）
- `--mode kaitori-up` 買取上昇のみ
- `--mode price-anomaly` 価格異常値のみ
- `--mode new-release` 新商品のみ
- `--mode sale` セールのみ
- `--mode price-drop` EC下落のみ
- `--mode restock` 在庫切れ復活のみ
- `--mode kaitori-disappear` 買取店消失のみ
- `--mode discontinued` 生産終了品のみ
- `--mode mercari-density` メルカリ急増のみ
- `--mode cross-mall` モール横断レポート（検索せずに終了）

**メルカリ出品数蓄積（戦略M用）**:
```bash
python mercari_scraper.py --top 200   # 利益候補スコア上位200件の出品数を取得
```
`~/.kaitori-viewer/mercari_history.json` に追記（最大30件/JAN）。`_mercari_worker.py` がPlaywrightサブプロセスで実行。3サンプル以上溜まると戦略Mが機能する。

**スナップショット自動蓄積（戦略E/O用）**:
`auto_extract.py` 起動時に `save_snapshot()` が自動実行。`all_data_*.csv` が複数ある場合は `bootstrap_from_csv_files()` で既存データからも履歴生成可能。

### 追加戦略 (J/K/L/N/Q/R)

20戦略に拡張。hybrid モードに以下も自動統合:

14. **戦略J (auction)**: `auction_relay_detector.py` — `auction_history.json` から、ヤフオク落札中央値 - 1000円 > 買取価格 のJANを抽出。買取→ヤフオク直販で利益確保候補。事前に `python yauc_scraper.py --top N` で履歴蓄積必要。`_yauc_worker.py` がPlaywrightサブプロセスでbot対策付き取得
15. **戦略K (stock-tight)**: `stock_tightness_detector.py` — `ec_cache.json` から商品名「残り3点」等の在庫切迫JANを検出。`_worker_common.extract_stock_number()` で正規表現抽出済み（ec_search.py の楽天/Yahoo エントリに `stock_count` 追加済み）
16. **戦略L (seasonal)**: `campaign_calendar.get_seasonal_boost()` — 月別×カテゴリ/商品名のマッピング（10月→暖房、12月→ゲーム機等）でスコアブースト1.0〜1.5倍。翌月マッチは半減効果（先取り需要）。戦略A+Dに乗算適用
17. **戦略N (review-spike)**: `review_spike_detector.py` — `ec_search.py` で取得した `review_count` を `review_history.json` に蓄積し、+10件以上の急増JANを検出。バズ商品の早期発見
18. **戦略Q (name-match)**: `name_matcher.py` — JANなしCSV行の商品名で楽天/Yahoo APIをキーワード検索し、`rapidfuzz.fuzz.token_set_ratio` で類似度80%以上の最高一致からJAN救済。Gemini不使用、API費用ゼロ。`requirements.txt` に rapidfuzz>=3.0.0 追加
19. **戦略R (suruga-ya)**: `secondhand_arbitrage_detector.py` — `secondhand_history.json` から駿河屋中古価格 - 500円 > 買取価格のJAN抽出。レトロゲーム/トレカ/フィギュア等の対象カテゴリを `is_target_category()` でフィルタ。事前に `python suruga_ya_scraper.py --top N` で履歴蓄積必要

実行例（追加分）:
- `--mode auction` ヤフオク利益確定のみ
- `--mode stock-tight` 在庫切迫のみ
- `--mode review-spike` レビュー急増のみ
- `--mode suruga-ya` 駿河屋利益確定のみ

**履歴データ蓄積コマンド**:
```bash
python yauc_scraper.py --top 30          # ヤフオク落札中央値（戦略J、bot対策のため1並列）
python suruga_ya_scraper.py --top 50     # 駿河屋価格（戦略R、対象カテゴリ自動フィルタ）
python mercari_scraper.py --top 200      # メルカリ出品数（戦略M）
```

**戦略L（季節）の判定**:
- 当月マッチ: フルブースト（例: 7月の「夏」→ x1.5）
- 翌月マッチ: 効果半減（先取り需要、例: 4月の「扇風機」→ x1.15）
- マッチなし: x1.0
- マッピングは `campaign_calendar._SEASONAL_BOOST_MAP` で編集可能

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
