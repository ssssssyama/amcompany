"""バックグラウンド利益商品自動抽出CLI

使い方:
    python auto_extract.py
    python auto_extract.py --threshold 5000 --shipping 1500
    python auto_extract.py --top 100 --shops 商店 森森 ルデヤ
    python auto_extract.py --rakuten-bonus 10 --yahoo-bonus 7
"""

import argparse
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from csv_loader import SHOP_NAMES, is_excluded, load_csv
from ec_search import batch_search_ec_prices
from profit import calculate_cash_profit, is_above_threshold

_LOCAL_DATA_DIR = Path.home() / ".kaitori-viewer"
_LOCAL_DATA_DIR.mkdir(exist_ok=True)
CACHE_FILE = _LOCAL_DATA_DIR / "cache_results.json"
LOG_DIR = _LOCAL_DATA_DIR / "logs"

# 量販店ECの検索URLテンプレート（{JAN}がJANコードに置換される）
EC_SEARCH_URLS = {
    "価格.com": "https://search.kakaku.com/{JAN}/",
    "Amazon": "https://www.amazon.co.jp/s?k={JAN}",
    "ヨドバシ": "https://www.yodobashi.com/?word={JAN}",
    "ビックカメラ": "https://www.biccamera.com/bc/category/?q={JAN}",
    "ケーズデンキ": "https://www.ksdenki.com/shop/e/search/?keyword={JAN}",
    "ジョーシン": "https://joshinweb.jp/servlet/emall/search?keyword={JAN}",
    "ノジマ": "https://online.nojima.co.jp/app/catalog/list/init?searchWord={JAN}",
    "エディオン": "https://www.edion.com/item_list.html?keyword={JAN}",
    "ソフマップ": "https://www.sofmap.com/search_result.aspx?keyword={JAN}",
    "コジマ": "https://www.kojima.net/ec/index.html?keyword={JAN}",
    "Qoo10": "https://www.qoo10.jp/s/{JAN}?keyword={JAN}",
    "auPAYマーケット": "https://wowma.jp/itemlist?e_scope=O&keyword={JAN}",
    "ツクモ": "https://shop.tsukumo.co.jp/goods/{JAN}/",   # JAN直URL方式、実機検証済み
    "駿河屋": "https://www.suruga-ya.jp/search?search_word={JAN}",   # 新品のみ（中古厳格除外）
    "サウンドハウス": "https://www.soundhouse.co.jp/search/index/keyword/{JAN}",  # Chrome拡張巡回（anti-bot強）
    "e☆イヤホン": "https://www.e-earphone.jp/search?keyword={JAN}",  # Chrome拡張巡回（SPA）
    "ムラウチ": "https://www.murauchi.com/MCJ/product/detail.do?jan_code={JAN}",  # Chrome拡張巡回（CAPTCHA）
    "セブンネット": "https://7net.omni7.jp/search/?keyword={JAN}",   # Chrome拡張巡回
    "フジヤカメラ": "https://www.fujiya-camera.co.jp/shop/goods/search.aspx?keyword={JAN}",  # Chrome拡張巡回
    "楽天ブックス": "https://books.rakuten.co.jp/search?sitem={JAN}",  # Chrome拡張巡回
    # 以下4サイトは誤検出リスクのため一時無効化:
    # 復活時は実HTML調査 + JAN/商品名一致検証 + 価格妥当性チェックを追加してから再登録
    # "ドスパラ": "https://www.dospara.co.jp/products/all-item?q={JAN}",  # GPU単体 vs PC本体の価格桁違い誤マッチ懸念
    # "パソコン工房": "https://www.pc-koubou.jp/products/list.php?keyword={JAN}",  # JS遅延描画で価格取れず
    # "マップカメラ": "https://www.mapcamera.com/search?keyword={JAN}",  # DNS解決不安定
    # "キタムラ": "https://shop.kitamura.jp/ja/search/?keywords={JAN}",  # 完全SPAで価格抽出困難
    "ハードオフ": "https://netmall.hardoff.co.jp/search/?q={JAN}",  # 旧 keyword= は機能しない、q= に変更
}
CSV_DIR = Path(__file__).resolve().parent.parent.parent


def load_cache() -> list:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def load_cache_clean() -> list:
    """キャッシュを読み込み、価格比率が疑わしいエントリを自動削除する。

    過去に誤検出されて混入したエントリ（MacBook Pro買取358,000円 → sokutei 59,800円 等）を
    起動時に掃除する。閾値は `filters.py` に集約。
    """
    from filters import check_ratio as _check_ratio
    data = load_cache()
    if not data:
        return data
    clean = []
    removed = 0
    for r in data:
        k = r.get("最高買取価格", 0) or 0
        p = r.get("EC最安値", 0) or 0
        if k > 0 and p > 0:
            rc = _check_ratio(int(k), int(p))
            if rc["suspicious"]:
                logging.getLogger(__name__).warning(
                    "[キャッシュ掃除] 削除: JAN %s %s [%s] %s",
                    r.get("JAN", "?"), rc["reason"],
                    r.get("ECソース", "?"), str(r.get("商品名", ""))[:40],
                )
                removed += 1
                continue
        clean.append(r)
    if removed:
        logging.getLogger(__name__).warning(
            "[キャッシュ掃除] %d 件のratio異常エントリを削除", removed,
        )
        save_cache(clean)
    return clean


def _cache_file_lock():
    """クロスプラットフォームのファイルロック（ベストエフォート）

    filelock パッケージがあればそれを使う。無ければ no-op contextmanager を返す。
    auto_extract と price_server の同時書き込みによる Lost Update を防ぐ。
    """
    import contextlib
    try:
        from filelock import FileLock
        lock_path = str(CACHE_FILE) + ".lock"
        return FileLock(lock_path, timeout=10)
    except ImportError:
        # ライブラリ無しでも動くように no-op context manager
        @contextlib.contextmanager
        def _nolock():
            yield
        return _nolock()


def save_cache(data: list):
    """一括保存（マージせず上書き）。内部処理用。

    プロセス間での Chrome拡張との競合を避けたい場合は `save_cache_merge` を使うこと。
    """
    try:
        with _cache_file_lock():
            tmp = CACHE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(CACHE_FILE)
    except OSError as e:
        logging.getLogger(__name__).warning("キャッシュ保存失敗（ディスク容量不足？）: %s", e)


def save_cache_merge(new_items: list):
    """差分マージ保存: 保存直前にディスクを再読み込みして、
    自分が持たないJAN（Chrome拡張が追加したもの等）を残したまま書き込む。

    これにより auto_extract.py と price_server.py が並行で書き込んでも
    互いのエントリを上書き消去しない（Lost Update 防止）。
    """
    try:
        with _cache_file_lock():
            # 書き込み直前にディスクから再読み込み
            try:
                disk = load_cache()
            except Exception:
                disk = []
            # JAN をキーにマージ: new_items を優先、ディスク側のみの JAN は残す
            seen_jans = {r.get("JAN") for r in new_items if r.get("JAN")}
            merged = list(new_items)
            for r in disk:
                j = r.get("JAN")
                if j and j not in seen_jans:
                    merged.append(r)
            # アトミック書き込み
            tmp = CACHE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(CACHE_FILE)
    except OSError as e:
        logging.getLogger(__name__).warning("キャッシュ保存失敗（ディスク容量不足？）: %s", e)


def bonus_points(ec_price: int, source: str, rakuten_rate: float, yahoo_rate: float) -> int:
    rates = {"楽天": rakuten_rate, "Yahoo": yahoo_rate}
    rate = rates.get(source, 0.0)
    return int(ec_price * rate / 100)


def _setup_logging():
    """コンソール + ファイルのログ設定

    - 従来の extract_*.log（auto_extract 単体ログ）に加えて、
      run.py から起動された場合は KAITORI_LOG_FILE の共通ログにも追記する。
    """
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # run.py から起動された場合、共通ログファイルにも追記
    try:
        from log_utils import attach_to_log_file as _attach_log
        _attach_log(root)
    except Exception:
        pass

    return log_file


PRICE_SERVER_URL = "http://127.0.0.1:8502"


def _warn_if_chrome_not_running(log) -> None:
    """Chromeプロセスが走っていなければ警告を出す（Chrome拡張が動かない主因）"""
    try:
        import subprocess as _sp
        if sys.platform == "win32":
            r = _sp.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                        capture_output=True, text=True, timeout=5,
                        encoding="cp932", errors="ignore")
            running = "chrome.exe" in (r.stdout or "")
        else:
            r = _sp.run(["pgrep", "-f", "chrome|chromium"],
                        capture_output=True, text=True, timeout=5)
            running = bool((r.stdout or "").strip())
    except Exception:
        running = True  # 判定不能なら警告しない
        return
    if not running:
        log.warning("=" * 70)
        log.warning("⚠ Chrome が起動していません！Chrome拡張が動作できないためキューは消費されません")
        log.warning("  対処法:")
        log.warning("    1. Chromeブラウザを起動")
        log.warning("    2. chrome://extensions/ で「買取価格コレクター」を再読込（♻）")
        log.warning("    3. ビックカメラ等の対応サイトを1つ開く（background.jsがactive化）")
        log.warning("    または `python run.py --open-chrome` で自動起動")
        log.warning("=" * 70)


def _post_crawl_queue(jan_list: list[str], sites: list[str], log) -> bool:
    """price_server のクロールキューにJANを投入する。

    Chrome拡張の background.js が自動ポーリングで検知し巡回を開始する。

    Returns:
        True: 投入成功
        False: price_server 未起動等で失敗
    """
    import urllib.request

    # API トークン（price_server が生成したファイルから読み取る）
    token_file = Path.home() / ".kaitori-viewer" / "api_token"
    api_token = ""
    if token_file.exists():
        try:
            api_token = token_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass

    payload = json.dumps({"janList": jan_list, "sites": sites}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_token:
        headers["X-Kaitori-Token"] = api_token
    req = urllib.request.Request(
        f"{PRICE_SERVER_URL}/crawl_queue",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            log.info("[巡回] クロールキュー投入: %d件追加 (キュー合計%d件)",
                     result.get("added", 0), result.get("queued", 0))
            # Chrome拡張/Chromeプロセスが動いているか軽くチェック
            _warn_if_chrome_not_running(log)
            log.info("[巡回] Chrome拡張が5秒以内に自動ポーリングで巡回を開始します")
            return True
    except (ConnectionRefusedError, OSError) as e:
        # price_server 未起動時の接続拒否は通常状態のためサイレント
        # WinError 10061 (接続拒否) / ConnectionRefusedError 等をフィルタ
        msg = str(e)
        if "10061" in msg or "Connection refused" in msg or "拒否" in msg:
            log.debug("[巡回] price_server 未起動のためChrome拡張巡回をスキップ")
            return False
        log.warning("[巡回] クロールキュー投入失敗: %s", e)
        return False
    except Exception as e:
        log.warning("[巡回] クロールキュー投入失敗: %s", e)
        return False


def _queue_extension_crawl(jan_list: list[str], ec_map: dict, log):
    """全JANをChrome拡張の巡回キューに投入する。

    API/スクレイパーで結果が取れたJANでも、ブロック済みサイト（ビックカメラ等）に
    より安い価格がある可能性があるため、全件を巡回対象にする。

    price_server が起動中なら POST /crawl_queue で投入。
    Chrome拡張の background.js が自動ポーリングで巡回を開始する。
    price_server が未起動の場合は何もしない（サイレント）。
    """
    from retailers import EXTENSION_ONLY_RETAILERS

    if not jan_list:
        return

    sites = EXTENSION_ONLY_RETAILERS
    if _post_crawl_queue(jan_list, sites, log):
        log.info("[拡張巡回] %d件のJANをChrome拡張の巡回キューに投入しました（%sサイト対象）",
                 len(jan_list), len(sites))


def _wait_crawl_completion(jan_list: list[str], sites: list[str], log, timeout: int = 600):
    """Chrome拡張の巡回完了を待つ。

    キャッシュに結果が蓄積されるのを監視して進捗を表示する。
    """
    import urllib.request

    total_expected = len(jan_list) * len(sites)
    start_cache_count = len(load_cache())
    start_time = time.time()

    log.info("[巡回] 待機中... (最大%d秒、Chrome拡張が%d件のURLを巡回予定)",
             timeout, total_expected)

    server_failures = 0
    while time.time() - start_time < timeout:
        time.sleep(10)

        current_cache = load_cache()
        new_results = len(current_cache) - start_cache_count
        elapsed = int(time.time() - start_time)

        # price_server のステータスを確認
        try:
            req = urllib.request.Request(f"{PRICE_SERVER_URL}/status")
            with urllib.request.urlopen(req, timeout=3) as resp:
                status = json.loads(resp.read())
                cache_count = status.get("cache_count", 0)
            server_failures = 0
        except Exception:
            cache_count = len(current_cache)
            server_failures += 1
            if server_failures >= 3:
                log.warning("[巡回] price_server に接続できません。巡回待機を終了します。")
                break

        log.info("[巡回] %d秒経過: 新規結果 +%d件 (キャッシュ合計%d件)",
                 elapsed, new_results, cache_count)

        # 全JAN がキャッシュに載ったら完了
        cached_jans = {r.get("JAN") for r in current_cache}
        remaining = [j for j in jan_list if j not in cached_jans]
        if not remaining:
            log.info("[巡回] 全JAN の結果を受信完了")
            break

    elapsed = int(time.time() - start_time)
    final_cache = load_cache()
    new_total = len(final_cache) - start_cache_count
    log.info("[巡回] 巡回完了: %d秒, 新規結果 +%d件", elapsed, new_total)


def _select_targets(df, args, sort_key, log) -> list[str]:
    """モードに応じて検索対象JANリストを優先度付きで選定する。

    Args:
        df: フィルタ済みのDataFrame（買取店/除外/カテゴリフィルタ適用済み）
        args: CLI引数
        sort_key: ソートキー名（"利益候補スコア"）
        log: ロガー

    Returns:
        優先度順のJANリスト（最大args.top件）
    """
    selected: list[str] = []
    csv_jans = set(df["JAN"].tolist())

    # 戦略E: 買取価格上昇検知（スナップショット保存も同時実行）
    if args.mode in ("kaitori-up", "hybrid"):
        try:
            from kaitori_upward_detector import save_snapshot, detect_kaitori_increases
            save_snapshot(df)
            increases = detect_kaitori_increases(min_increase_pct=5.0)
            up_limit = args.top if args.mode == "kaitori-up" else min(50, args.top // 4)
            added = 0
            for jan, pct in increases:
                if jan in csv_jans and jan not in selected:
                    selected.append(jan)
                    added += 1
                    if added >= up_limit:
                        break
            log.info("[戦略E] 買取上昇商品: %d件追加 (履歴%d件)",
                     added, len(increases))
        except Exception as e:
            log.warning("[戦略E] 買取上昇検知失敗: %s", e)

    # 戦略J: ヤフオク利益確定（買取→ヤフオク直販）
    if args.mode in ("auction", "hybrid"):
        try:
            from auction_relay_detector import detect_auction_arbitrage
            arb = detect_auction_arbitrage(min_gap=1000)
            arb_limit = args.top if args.mode == "auction" else min(30, args.top // 5)
            added = 0
            for jan, _med, _kai in arb:
                if jan in csv_jans and jan not in selected:
                    selected.append(jan)
                    added += 1
                    if added >= arb_limit:
                        break
            log.info("[戦略J] ヤフオク利益確定: %d件追加 (候補%d件)", added, len(arb))
        except Exception as e:
            log.warning("[戦略J] ヤフオク利益確定検知失敗: %s", e)

    # 戦略K: 在庫切迫（残り3点以下）
    if args.mode in ("stock-tight", "hybrid"):
        try:
            from stock_tightness_detector import detect_stock_tightness
            tight = detect_stock_tightness(max_stock=3)
            tight_limit = args.top if args.mode == "stock-tight" else min(20, args.top // 5)
            added = 0
            for jan, _stock in tight:
                if jan in csv_jans and jan not in selected:
                    selected.append(jan)
                    added += 1
                    if added >= tight_limit:
                        break
            log.info("[戦略K] 在庫切迫: %d件追加 (候補%d件)", added, len(tight))
        except Exception as e:
            log.warning("[戦略K] 在庫切迫検知失敗: %s", e)

    # 戦略P: EC価格異常値検知（相場40%以下）
    if args.mode in ("price-anomaly", "hybrid"):
        try:
            from price_anomaly_detector import detect_price_anomalies
            anomalies = detect_price_anomalies(threshold_pct=40.0)
            anom_limit = args.top if args.mode == "price-anomaly" else min(30, args.top // 5)
            added = 0
            for jan, _cur, _med, _ratio in anomalies:
                if jan in csv_jans and jan not in selected:
                    selected.append(jan)
                    added += 1
                    if added >= anom_limit:
                        break
            log.info("[戦略P] 価格異常値: %d件追加 (候補%d件)", added, len(anomalies))
        except Exception as e:
            log.warning("[戦略P] 価格異常値検知失敗: %s", e)

    # 戦略I: 新商品・予約商品検知
    if args.mode in ("new-release", "hybrid"):
        try:
            from new_release_finder import find_new_releases
            new_jans = find_new_releases(csv_jans, days_within=30)
            nr_limit = args.top if args.mode == "new-release" else min(30, args.top // 5)
            added = 0
            for jan in new_jans:
                if jan not in selected:
                    selected.append(jan)
                    added += 1
                    if added >= nr_limit:
                        break
            log.info("[戦略I] 新商品: %d件追加", added)
        except Exception as e:
            log.warning("[戦略I] 新商品検知失敗: %s", e)

    # 戦略B: セール中のJAN（ランキング∩CSV）
    if args.mode in ("sale", "hybrid"):
        try:
            from sale_finder import find_sale_intersections
            sale_jans = find_sale_intersections(csv_jans)
            # CSV内にあるJANのみ（既にfind_sale_intersectionsでフィルタ済み）
            sale_limit = args.top if args.mode == "sale" else min(50, args.top // 4)
            for j in sale_jans[:sale_limit]:
                if j not in selected:
                    selected.append(j)
            log.info("[戦略B] セール商品: %d件追加", len(selected))
        except Exception as e:
            log.warning("[戦略B] セール検索失敗: %s", e)

    # 戦略C: 価格下落中のJAN
    if args.mode in ("price-drop", "hybrid"):
        try:
            from price_drop_detector import detect_price_drops
            drops = detect_price_drops(min_drop_pct=10.0)
            drop_limit = args.top if args.mode == "price-drop" else min(50, args.top // 4)
            added = 0
            for jan, pct in drops:
                if jan in csv_jans and jan not in selected:
                    selected.append(jan)
                    added += 1
                    if added >= drop_limit:
                        break
            log.info("[戦略C] 価格下落商品: %d件追加", added)
        except Exception as e:
            log.warning("[戦略C] 価格下落検知失敗: %s", e)

    # 戦略G: 在庫切れ復活監視
    if args.mode in ("restock", "hybrid"):
        try:
            from restock_monitor import get_restock_candidates
            restocks = get_restock_candidates(min_profit=1000)
            restock_limit = args.top if args.mode == "restock" else min(20, args.top // 5)
            added = 0
            for jan in restocks:
                if jan in csv_jans and jan not in selected:
                    selected.append(jan)
                    added += 1
                    if added >= restock_limit:
                        break
            log.info("[戦略G] 在庫切れ復活: %d件追加 (候補%d件)",
                     added, len(restocks))
        except Exception as e:
            log.warning("[戦略G] 在庫切れ復活監視失敗: %s", e)

    # 戦略O: 買取店消失検知
    if args.mode in ("kaitori-disappear", "hybrid"):
        try:
            from kaitori_upward_detector import detect_kaitori_disappearances
            disappeared = detect_kaitori_disappearances(min_prev_shops=3)
            dis_limit = args.top if args.mode == "kaitori-disappear" else min(15, args.top // 10)
            added = 0
            for jan in disappeared:
                if jan in csv_jans and jan not in selected:
                    selected.append(jan)
                    added += 1
                    if added >= dis_limit:
                        break
            log.info("[戦略O] 買取店消失JAN: %d件追加 (候補%d件)",
                     added, len(disappeared))
        except Exception as e:
            log.warning("[戦略O] 買取店消失検知失敗: %s", e)

    # 戦略T: 生産終了品（希少化シグナル）
    if args.mode in ("discontinued", "hybrid"):
        try:
            if "生産終了" in df.columns:
                disc_df = df[df["生産終了"] == True].sort_values(sort_key, ascending=False)
                disc_limit = args.top if args.mode == "discontinued" else min(20, args.top // 10)
                added = 0
                for jan in disc_df["JAN"].tolist():
                    if jan not in selected:
                        selected.append(jan)
                        added += 1
                        if added >= disc_limit:
                            break
                log.info("[戦略T] 生産終了品: %d件追加 (候補%d件)",
                         added, len(disc_df))
        except Exception as e:
            log.warning("[戦略T] 生産終了品検知失敗: %s", e)

    # 戦略N: レビュー数ジャンプ（ec_cache から履歴保存も実行）
    if args.mode in ("review-spike", "hybrid"):
        try:
            from review_spike_detector import save_review_snapshot, detect_review_spikes
            save_review_snapshot()
            spikes = detect_review_spikes(min_increase=10)
            n_limit = args.top if args.mode == "review-spike" else min(20, args.top // 5)
            added = 0
            for jan, _cur, _inc in spikes:
                if jan in csv_jans and jan not in selected:
                    selected.append(jan)
                    added += 1
                    if added >= n_limit:
                        break
            log.info("[戦略N] レビュー急増: %d件追加 (候補%d件)", added, len(spikes))
        except Exception as e:
            log.warning("[戦略N] レビュー急増検知失敗: %s", e)

    # 戦略R: 駿河屋中古市場アービトラージ
    if args.mode in ("suruga-ya", "hybrid"):
        try:
            from secondhand_arbitrage_detector import detect_secondhand_arbitrage
            sec = detect_secondhand_arbitrage(min_gap=500)
            r_limit = args.top if args.mode == "suruga-ya" else min(20, args.top // 5)
            added = 0
            for jan, _used in sec:
                if jan in csv_jans and jan not in selected:
                    selected.append(jan)
                    added += 1
                    if added >= r_limit:
                        break
            log.info("[戦略R] 駿河屋利益確定: %d件追加 (候補%d件)", added, len(sec))
        except Exception as e:
            log.warning("[戦略R] 駿河屋利益確定検知失敗: %s", e)

    # 戦略M: メルカリ出品密度急増
    if args.mode in ("mercari-density", "hybrid"):
        try:
            from mercari_density_detector import detect_density_spikes
            spikes = detect_density_spikes(min_increase_pct=50.0)
            m_limit = args.top if args.mode == "mercari-density" else min(30, args.top // 5)
            added = 0
            for jan, _count, _pct in spikes:
                if jan in csv_jans and jan not in selected:
                    selected.append(jan)
                    added += 1
                    if added >= m_limit:
                        break
            log.info("[戦略M] メルカリ急増: %d件追加 (候補%d件)",
                     added, len(spikes))
        except Exception as e:
            log.warning("[戦略M] メルカリ密度検知失敗: %s", e)

    # 戦略A+D: スコア上位（残り枠を埋める）
    # + 戦略H: pointRate≥10ブースト
    # + 戦略Z: 過去成功パターンで再スコアリング
    if args.mode in ("default", "hybrid"):
        remaining = args.top - len(selected)
        if remaining > 0:
            # 戦略H: ec_cache から pointRate≥10 のJANを抽出
            # 戦略K強化: stock_count <= 3 のJAN（在庫切迫）を最優先
            try:
                from ec_search import _load_ec_cache, _ec_cache
                _load_ec_cache()
                high_pt_jans = {
                    jan for jan, e in _ec_cache.items()
                    if isinstance(e, dict) and (e.get("point_rate", 1) or 1) >= 10
                }
                tight_stock_jans = {
                    jan for jan, e in _ec_cache.items()
                    if isinstance(e, dict)
                    and isinstance(e.get("stock_count"), int)
                    and 1 <= e["stock_count"] <= 3
                }
            except Exception:
                high_pt_jans = set()
                tight_stock_jans = set()

            # 戦略Z: 過去成功パターンモデル
            try:
                from success_pattern_scorer import build_pattern_model, score_jan
                pattern_model = build_pattern_model()
            except Exception:
                pattern_model = {"total": 0}

            # 戦略L: 季節ブースト
            try:
                from campaign_calendar import get_seasonal_boost
                _get_seasonal = get_seasonal_boost
            except Exception:
                _get_seasonal = lambda c, n="": 1.0

            df_score = df.copy()
            df_score["_boosted_score"] = df_score.apply(
                lambda r: (
                    r[sort_key]
                    * (1.5 if r["JAN"] in high_pt_jans else 1.0)
                    * (2.0 if r["JAN"] in tight_stock_jans else 1.0)  # 戦略K: 在庫切迫2倍ブースト
                    * score_jan(r, pattern_model)
                    * _get_seasonal(str(r.get("カテゴリ", "") or ""), str(r.get("商品名", "") or ""))
                ),
                axis=1,
            )
            score_jans = df_score.sort_values("_boosted_score", ascending=False)["JAN"].tolist()

            if tight_stock_jans:
                log.info("[戦略K] 在庫切迫(残≤3点): %d件をスコア2倍ブースト", len(tight_stock_jans))
            if high_pt_jans:
                log.info("[戦略H] ポイント10倍以上: %d件をスコア1.5倍ブースト", len(high_pt_jans))
            if pattern_model.get("total", 0) >= 5:
                log.info("[戦略Z] 成功パターン再スコア: %d件の過去利益から学習", pattern_model["total"])
            log.info("[戦略L] 季節ブースト適用 (現在月の需要にマッチするJANを優遇)")

            score_added = 0
            for jan in score_jans:
                if jan not in selected:
                    selected.append(jan)
                    score_added += 1
                    if score_added >= remaining:
                        break
            log.info("[戦略A+D] スコア上位: %d件追加", score_added)

    return selected[:args.top]


def main():
    parser = argparse.ArgumentParser(description="利益商品自動抽出")
    parser.add_argument("--csv", type=str, default="", help="CSVファイルパス（省略時は最新）")
    parser.add_argument("--threshold", type=int, default=1000, help="最低利益閾値(円)")
    parser.add_argument("--shipping", type=int, default=1000, help="送料合計(円)")
    parser.add_argument("--top", type=int, default=200, help="検索件数（利益候補スコア上位N件）")
    parser.add_argument("--shops", nargs="*", default=None, help="利用する買取店（省略時は全店）")
    parser.add_argument("--rakuten-bonus", type=float, default=None, help="楽天ボーナスPT(%%)。省略時はキャンペーンカレンダーから自動算出")
    parser.add_argument("--yahoo-bonus", type=float, default=None, help="Yahoo!ボーナスPT(%%)。省略時はキャンペーンカレンダーから自動算出")
    parser.add_argument("--pt-threshold", type=int, default=0, help="PT込利益の閾値(円)。指定時はPT込利益で判定")
    parser.add_argument("--min-kaitori", type=int, default=5000, help="買取価格の下限(円)。これ未満の商品はスキップ")
    parser.add_argument("--no-scraper", action="store_true", help="スクレイパー(Amazon/ヨドバシ)を無効化。API(楽天/Yahoo)のみで高速検索")
    parser.add_argument("--open-browser", type=int, default=0, metavar="N",
                        help="利益上位N件の量販店検索URLをブラウザで開く（例: --open-browser 5）")
    parser.add_argument("--ec-sites", nargs="*", default=list(EC_SEARCH_URLS.keys()),
                        help=f"ブラウザで開くECサイト（デフォルト: 全サイト）。選択肢: {', '.join(EC_SEARCH_URLS.keys())}")
    parser.add_argument("--clear-cache", action="store_true", help="キャッシュをクリアしてから実行")
    parser.add_argument("--wait-extension", action="store_true",
                        help="Chrome拡張の巡回完了まで待機（price_serverにキュー投入後、結果がcacheに蓄積されるのを待つ）")
    parser.add_argument("--extension-timeout", type=int, default=300,
                        help="Chrome拡張巡回の最大待機秒数（デフォルト300秒）")
    parser.add_argument("--categories", nargs="*",
                        default=["all"],
                        help="検索対象カテゴリキーワード（カテゴリ名に含まれていればマッチ）。"
                             "デフォルト: all (全カテゴリ対象)。"
                             "特定カテゴリに絞る例: --categories カメラ ゲーム グラフィックボード")
    parser.add_argument("--mode",
                        choices=["default", "sale", "price-drop", "restock",
                                 "kaitori-up", "cross-mall", "new-release",
                                 "price-anomaly", "mercari-density",
                                 "discontinued", "kaitori-disappear",
                                 "auction", "stock-tight", "review-spike",
                                 "suruga-ya", "mercari-resale", "hybrid"],
                        default="hybrid",
                        help="検索対象選定モード: "
                             "default=スコア上位のみ, "
                             "sale=楽天/Yahooセール商品, "
                             "price-drop=EC価格下落商品, "
                             "restock=過去利益JANで在庫切れのもの, "
                             "kaitori-up=買取価格が上昇したJAN, "
                             "cross-mall=楽天/Yahoo価格差レポート（検索せず終了）, "
                             "new-release=発売直近30日以内の新商品, "
                             "price-anomaly=EC価格が相場の40%%以下の異常値, "
                             "mercari-density=メルカリ出品数急増, "
                             "discontinued=生産終了品（希少化シグナル）, "
                             "kaitori-disappear=買取店が扱わなくなったJAN, "
                             "hybrid=全ソース統合（デフォルト）")
    parser.add_argument("--browse", type=int, default=0, metavar="N",
                        help="買取候補スコア上位N件をブラウザで開いて目視確認（EC検索不要）")
    parser.add_argument("--crawl", type=int, default=0, metavar="N",
                        help="Chrome拡張巡回モード: 上位N件の量販店ページを実ブラウザで順番に開き価格を自動収集")
    args = parser.parse_args()

    # キャンペーンカレンダーでボーナス率を自動算出（手動指定がない場合）
    from campaign_calendar import get_bonus_rates, get_active_campaigns

    if args.rakuten_bonus is None or args.yahoo_bonus is None:
        rates = get_bonus_rates()
        if args.rakuten_bonus is None:
            args.rakuten_bonus = rates["rakuten"]
        if args.yahoo_bonus is None:
            args.yahoo_bonus = rates["yahoo"]

    log = logging.getLogger(__name__)
    log_file = _setup_logging()

    # メルカリ転売モード: ハードオフ仕入 → メルカリ販売の利益候補を独立フローで検索
    if args.mode == "mercari-resale":
        from mercari_resale_finder import find_mercari_resale_candidates

        if args.csv:
            csv_path = Path(args.csv)
        else:
            csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
            if not csv_files:
                log.error("CSVファイルが見つかりません。")
                sys.exit(1)
            csv_path = csv_files[0]

        df = load_csv(str(csv_path))
        df = df[df["最高買取価格"] >= args.min_kaitori]
        df = df[~df.apply(lambda r: is_excluded(r["商品名"], r.get("カテゴリ", "")), axis=1)]
        if args.categories and args.categories != ["all"]:
            df = df[df["カテゴリ"].apply(
                lambda c: any(kw in str(c) for kw in args.categories) if c else False
            )]

        sort_key = "利益候補スコア" if "利益候補スコア" in df.columns else "最高買取価格"
        target_jans = df.sort_values(sort_key, ascending=False).head(args.top)["JAN"].tolist()

        log.info("=== メルカリ転売候補レポート（ハードオフ仕入）===")
        log.info("対象: %d件のJANをハードオフで検索中...", len(target_jans))
        candidates = find_mercari_resale_candidates(
            target_jans, df,
            min_profit=args.threshold,
            shipping_cost=args.shipping,
        )
        log.info("")
        log.info("発見: %d件の転売候補（利益≥%s円）", len(candidates), f"{args.threshold:,}")
        for c in candidates[:30]:
            log.info("  %s: 利益%s円 (仕入%s → メルカリ%s) ランク%s | %s",
                     c["JAN"], f"{c['メルカリ予想利益']:+,}",
                     f"{c['ハードオフ仕入価格']:,}", f"{c['メルカリ予想販売価格']:,}",
                     c["中古ランク"] or "-", c["商品名"][:30])
        log.info("\n保存先: ~/.kaitori-viewer/mercari_resale_results.json")
        return

    # 戦略F: モール横断アービトラージレポート（独立モード）
    if args.mode == "cross-mall":
        from mall_arbitrage import find_mall_gaps

        if args.csv:
            csv_path = Path(args.csv)
        else:
            csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
            if not csv_files:
                log.error("CSVファイルが見つかりません。")
                sys.exit(1)
            csv_path = csv_files[0]

        df = load_csv(str(csv_path))
        df = df[df["最高買取価格"] >= args.min_kaitori]
        df = df[~df.apply(lambda r: is_excluded(r["商品名"], r.get("カテゴリ", "")), axis=1)]
        if args.categories and args.categories != ["all"]:
            df = df[df["カテゴリ"].apply(
                lambda c: any(kw in str(c) for kw in args.categories) if c else False
            )]

        sort_key = "利益候補スコア" if "利益候補スコア" in df.columns else "最高買取価格"
        target_jans = df.sort_values(sort_key, ascending=False).head(args.top)["JAN"].tolist()

        log.info("=== モール横断アービトラージレポート ===")
        log.info("対象: %d件のJAN（楽天/Yahoo価格を比較）", len(target_jans))
        gaps = find_mall_gaps(target_jans, min_gap=2000)
        log.info("")
        log.info("発見: %d件の価格差候補", len(gaps))
        for g in gaps[:30]:
            log.info("  %s: 差%s円 (楽天%s vs Yahoo%s) → %sで買い→%sで売り | %s",
                     g["jan"], f"{g['gap']:,}",
                     f"{g['rakuten_price']:,}", f"{g['yahoo_price']:,}",
                     g["buy_at"], g["sell_at"], g["name"][:30])
        return

    # --crawl: Chrome拡張巡回 + API/スクレイパー並行実行モード
    if args.crawl > 0:
        import threading
        import webbrowser as _wb

        # CSV読み込み
        if args.csv:
            csv_path = Path(args.csv)
        else:
            csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
            if not csv_files:
                log.error("CSVファイルが見つかりません。")
                sys.exit(1)
            csv_path = csv_files[0]

        df = load_csv(str(csv_path))

        # 買取店フィルタ
        selected_shops = args.shops if args.shops is not None else list(SHOP_NAMES)
        if set(selected_shops) != set(SHOP_NAMES):
            shop_price_cols = [f"{s}_価格" for s in selected_shops if f"{s}_価格" in df.columns]
            if shop_price_cols:
                df["最高買取価格"] = df[shop_price_cols].max(axis=1)
                df = df[df["最高買取価格"] > 0]

        # フィルタ
        df = df[df["最高買取価格"] >= args.min_kaitori]
        df = df[~df.apply(lambda r: is_excluded(r["商品名"], r.get("カテゴリ", "")), axis=1)]

        # カテゴリフィルタ
        if args.categories and args.categories != ["all"]:
            df = df[df["カテゴリ"].apply(
                lambda c: any(kw in str(c) for kw in args.categories) if c else False
            )]

        sort_key = "利益候補スコア" if "利益候補スコア" in df.columns else "最高買取価格"
        targets = df.sort_values(sort_key, ascending=False).head(args.crawl)
        target_rows = {row["JAN"]: row for _, row in targets.iterrows()}
        jan_list = list(target_rows.keys())

        # 既にキャッシュ済みのJANを除外（巡回用）
        cached = {r["JAN"] for r in load_cache_clean() if "JAN" in r}
        uncached_jans = [j for j in jan_list if j not in cached]

        CRAWL_SITES = {
            "ビックカメラ": "https://www.biccamera.com/bc/category/?q={JAN}",
            "ケーズデンキ": "https://www.ksdenki.com/shop/e/search/?keyword={JAN}",
            "ジョーシン": "https://joshinweb.jp/servlet/emall/search?keyword={JAN}",
            "ノジマ": "https://online.nojima.co.jp/app/catalog/list/init?searchWord={JAN}",
            "エディオン": "https://www.edion.com/item_list.html?keyword={JAN}",
            "ソフマップ": "https://www.sofmap.com/search_result.aspx?keyword={JAN}",
            "コジマ": "https://www.kojima.net/ec/index.html?keyword={JAN}",
            "Qoo10": "https://www.qoo10.jp/s/{JAN}?keyword={JAN}",
            "auPAYマーケット": "https://wowma.jp/itemlist?e_scope=O&keyword={JAN}",
        }

        sites = [s for s in args.ec_sites if s in CRAWL_SITES] if args.ec_sites else list(CRAWL_SITES.keys())

        log.info("=== 並行検索 + Chrome拡張巡回モード ===")
        log.info("CSV: %s (%s件中 上位%s件)", csv_path.name, f"{len(df):,}", args.crawl)
        log.info("楽天/Yahoo API + スクレイパー（Amazon/ヨドバシ/価格.com）: バックグラウンド実行")
        log.info("Chrome拡張巡回（%s）: %s件", ", ".join(sites), len(uncached_jans))
        log.info("")

        # === バックグラウンド: 楽天/Yahoo API + スクレイパー ===
        api_results = []  # バックグラウンドスレッドの結果
        api_done = threading.Event()

        def _run_api_search():
            """楽天/Yahoo API + Amazon/ヨドバシ/価格.com スクレイパーを実行"""
            name_map = {jan: target_rows[jan]["商品名"] for jan in jan_list}
            # 利益判定は信頼買取価格（外れ値補正済み）をベースに
            price_map = {jan: int(target_rows[jan].get("信頼買取価格") or target_rows[jan]["最高買取価格"])
                         for jan in jan_list}

            log.info("[API] 楽天/Yahoo + スクレイパー 検索開始 (%s件, 2並列)", len(jan_list))

            def _on_result(jan, ec):
                if not ec:
                    return
                # 在庫切れでも利益商品は入荷待ちとしてキャッシュに残す
                row = target_rows[jan]
                max_kaitori = int(row["最高買取価格"])
                reliable_kaitori = int(row.get("信頼買取価格") or max_kaitori)
                is_outlier = bool(row.get("最高値_外れ値", False))
                # ★ハイブリッド: 利益判定は信頼価格ベース
                kaitori = reliable_kaitori
                pts = ec["points"] + bonus_points(ec["price"], ec["source"], args.rakuten_bonus, args.yahoo_bonus)
                profit_info = calculate_cash_profit(kaitori, ec["price"], args.shipping, pts)

                if not is_above_threshold(kaitori, ec["price"], args.threshold, args.shipping):
                    return

                # 売却チャネル判定（買取店 vs メルカリ）
                from profit import decide_sell_channel, calculate_card_rebate
                channel = decide_sell_channel(
                    kaitori_price=kaitori, ec_price=ec["price"],
                    category=row.get("カテゴリ", ""),
                    shipping_cost=args.shipping, points=pts,
                )
                # カード・ポイント還元
                card_rebate = calculate_card_rebate(ec["price"], ec["source"])
                # 上振れ余地: 最高買取が信頼買取より高い場合のボーナス可能性
                upside_bonus = max_kaitori - reliable_kaitori
                # プレミア化判定: 実ページから取れた定価より買取が高い = 希少化シグナル
                msrp = ec.get("msrp") or 0
                is_premium = bool(msrp and max_kaitori > msrp)
                item = {
                    "JAN": jan, "商品名": row["商品名"],
                    "最高買取価格": max_kaitori, "買取店": row["最高値店舗"],
                    # ハイブリッド: 利益計算に使った信頼価格と上振れ余地を明示
                    "信頼買取価格": reliable_kaitori,
                    "上振れ余地": upside_bonus,
                    "最高値_外れ値": is_outlier,
                    # プレミア化シグナル (定価 vs 買取)
                    "定価": int(msrp) if msrp else None,
                    "プレミア化": is_premium,
                    "買取_定価比": round(max_kaitori / msrp, 2) if msrp else None,
                    "買取確認": row.get("買取確認", ""),
                    "EC最安値": ec["price"], "EC店舗": ec["shop"],
                    "ECソース": ec["source"], "EC URL": ec["url"],
                    "ポイント": pts, "送料": args.shipping,
                    "現金利益": profit_info["cash_profit"],
                    "PT込利益": profit_info["profit_with_points"],
                    "ROI(%)": profit_info["roi"],
                    # 上振れが実現した場合の「ベストケース利益」
                    "上振れ時利益": profit_info["cash_profit"] + upside_bonus,
                    # カード・ポイント還元込み実質利益
                    "カード還元": card_rebate,
                    "実質利益": profit_info["cash_profit"] + pts + card_rebate,
                    # 売却チャネル比較
                    "推奨売却先": "メルカリ" if channel["recommended"] == "mercari" else "買取店",
                    "メルカリ想定売値": channel["mercari_estimate"],
                    "メルカリ想定利益": channel["mercari_profit"],
                    "売却差額": channel["advantage"],
                    "stock_status": ec.get("stock_status", "unknown"),
                    "在庫状況": {
                        "in_stock": "在庫あり", "limited": "残りわずか",
                        "out_of_stock": "在庫なし",
                    }.get(ec.get("stock_status", ""), "未確認"),
                    "商品リンク": ec["url"],
                    "取得日時": datetime.now().strftime("%m/%d %H:%M"),
                    # 収集経路マーカー（run.py サマリで分類）
                    "origin": "api" if ec.get("source") in ("楽天", "Yahoo") else "scraper",
                }
                api_results.append(item)
                upside_note = f" (上振れ+{upside_bonus:,}円)" if upside_bonus > 0 else ""
                log.info("[API] 利益発見: %s円 (PT込%s円)%s [%s] %s",
                         f"{profit_info['cash_profit']:+,}", f"{profit_info['profit_with_points']:+,}",
                         upside_note, ec["source"], row["商品名"][:35])
                # 通知（利益商品発見 + 在庫切迫時に別途）
                try:
                    from notifier import notify_profit, notify_tight_stock
                    notify_profit(
                        jan=jan, name=row["商品名"], price=ec["price"],
                        profit=profit_info["cash_profit"], url=ec.get("url", ""),
                        buyback_shop=row.get("最高値店舗", ""),
                        ec_source=ec.get("source", ""),
                    )
                    # 在庫切迫（残り3点以下）なら追加通知
                    sc = ec.get("stock_count")
                    if isinstance(sc, int) and 1 <= sc <= 3:
                        notify_tight_stock(
                            jan=jan, name=row["商品名"], stock_count=sc,
                            price=ec["price"], url=ec.get("url", ""),
                        )
                except Exception as e:
                    log.debug("通知失敗: %s", e)

            batch_search_ec_prices(
                jan_list,
                on_result=_on_result,
                product_names=name_map,
                kaitori_prices=price_map,
                threshold=args.threshold,
                shipping_cost=args.shipping,
                include_retailers=not args.no_scraper,
            )
            log.info("[API] 検索完了: %s件の利益商品を発見", len(api_results))
            api_done.set()

        api_thread = threading.Thread(target=_run_api_search, daemon=True)
        api_thread.start()

        # === メインスレッド: Chrome拡張巡回 ===
        if uncached_jans:
            log.info("[巡回] Chrome拡張巡回開始 (%s件 × %sサイト)", len(uncached_jans), len(sites))
            log.info("[巡回] Chrome拡張「買取価格コレクター」+ price_server が必要です")

            # price_server のクロールキューに投入 → Chrome拡張が自動ポーリングで巡回開始
            _crawl_queued = _post_crawl_queue(uncached_jans, sites, log)

            if _crawl_queued:
                # Chrome拡張の巡回完了を待つ（ポーリング）
                _wait_crawl_completion(uncached_jans, sites, log, timeout=600)
            else:
                # price_server 未起動の場合はフォールバック: 従来の webbrowser.open()
                log.warning("[巡回] price_server に接続できません。従来モードで巡回します。")
                import webbrowser as _wb
                total_urls = len(uncached_jans) * len(sites)
                opened = 0
                for jan in uncached_jans:
                    for site_name in sites:
                        url = CRAWL_SITES[site_name].replace("{JAN}", jan)
                        opened += 1
                        log.info("[巡回 %d/%d] %s %s", opened, total_urls, site_name, jan)
                        _wb.open(url)
                        time.sleep(random.uniform(5.0, 8.0))
                log.info("[巡回] 完了: %d件のURLを開きました", total_urls)
        else:
            log.info("[巡回] 全てキャッシュ済みのためスキップ")

        # === API検索の完了を待つ ===
        if not api_done.is_set():
            log.info("[待機] API検索の完了を待っています...")
            api_done.wait(timeout=300)

        # === 結果統合 ===
        # API結果をキャッシュに追加（Chrome拡張の結果は price_server 側で既に保存済み）
        all_results = list(load_cache())  # Chrome拡張巡回で蓄積された結果
        existing_jans = {r.get("JAN") for r in all_results}
        for item in api_results:
            if item["JAN"] not in existing_jans:
                all_results.append(item)
                existing_jans.add(item["JAN"])
            else:
                # 既存の結果よりAPI結果のほうが安ければ上書き
                for i, existing in enumerate(all_results):
                    if existing.get("JAN") == item["JAN"] and item.get("EC最安値", 0) < existing.get("EC最安値", float("inf")):
                        all_results[i] = item
                        break
        save_cache_merge(all_results)

        # === サマリー表示 ===
        profitable = [r for r in all_results if r.get("現金利益", 0) > 0]
        log.info("=" * 60)
        log.info("=== 完了 ===")
        log.info("API/スクレイパー利益商品: %s件", len(api_results))
        log.info("合計利益商品（Chrome拡張含む）: %s件", len(profitable))
        if profitable:
            sorted_p = sorted(profitable, key=lambda x: x.get("PT込利益", 0), reverse=True)
            for r in sorted_p[:20]:
                log.info("  %+8s円 (PT込%+8s円) 買取%8s円 EC%8s円 [%s] %s",
                         f"{r['現金利益']:,}", f"{r['PT込利益']:,}",
                         f"{r['最高買取価格']:,}", f"{r['EC最安値']:,}",
                         r.get("ECソース", "拡張"), r["商品名"][:35])
            if len(sorted_p) > 20:
                log.info("  ... 他%s件", len(sorted_p) - 20)
        log.info("結果: %s", CACHE_FILE)
        log.info("ログ: %s", log_file)
        sys.exit(0)

    # --browse: CSVの買取候補上位をブラウザで巡回し価格を自動取得
    if args.browse > 0:
        import re as _re

        # CSV読み込み
        if args.csv:
            csv_path = Path(args.csv)
        else:
            csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
            if not csv_files:
                log.error("CSVファイルが見つかりません。")
                sys.exit(1)
            csv_path = csv_files[0]

        df = load_csv(str(csv_path))

        # 買取店フィルタ
        selected_shops = args.shops if args.shops is not None else list(SHOP_NAMES)
        if set(selected_shops) != set(SHOP_NAMES):
            shop_price_cols = [f"{s}_価格" for s in selected_shops if f"{s}_価格" in df.columns]
            if shop_price_cols:
                df["最高買取価格"] = df[shop_price_cols].max(axis=1)
                df = df[df["最高買取価格"] > 0]

        # フィルタ
        df = df[df["最高買取価格"] >= args.min_kaitori]
        df = df[~df.apply(lambda r: is_excluded(r["商品名"], r.get("カテゴリ", "")), axis=1)]

        # ソート
        sort_key = "利益候補スコア" if "利益候補スコア" in df.columns else "最高買取価格"
        targets = df.sort_values(sort_key, ascending=False).head(args.browse)

        sites = [s for s in args.ec_sites if s in EC_SEARCH_URLS]
        _PAGE_TIMEOUT = 6000  # ページ読み込みタイムアウト(ms)

        log.info("=== ブラウザ巡回モード ===")
        log.info("CSV: %s (%s件中 上位%s件)", csv_path.name, f"{len(df):,}", len(targets))
        log.info("ECサイト: %s", ", ".join(sites))

        found_items = []

        try:
            from playwright.sync_api import sync_playwright

            from stealth import create_stealth_context

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=False, timeout=15000)
                try:
                    context = create_stealth_context(browser, viewport={"width": 1400, "height": 900})

                    for i, (_, row) in enumerate(targets.iterrows()):
                        jan = row["JAN"]
                        name = row["商品名"][:35]
                        kaitori = int(row["最高買取価格"])
                        shop = row["最高値店舗"]
                        log.info("[%d/%d] %s 買取%s円(%s) %s", i + 1, len(targets), jan, f"{kaitori:,}", shop, name)

                        best_price = None
                        best_site = ""

                        for site_name in sites:
                            url = EC_SEARCH_URLS[site_name].replace("{JAN}", jan)
                            page = context.new_page()
                            try:
                                page.goto(url, timeout=_PAGE_TIMEOUT, wait_until="domcontentloaded")
                                time.sleep(random.uniform(0.8, 2.0))

                                # 汎用価格抽出: ￥付き価格を探す
                                text = page.text_content("body") or ""
                                yen_matches = _re.findall(r"[￥¥](\d{1,3}(?:,\d{3})+)", text)
                                prices = [v for v in (int(m.replace(",", "")) for m in yen_matches) if v >= 1000]

                                if prices:
                                    price = min(prices)
                                    profit = kaitori - price - args.shipping
                                    mark = "◎" if profit >= args.threshold else "△" if profit > 0 else "✗"
                                    log.info("  %s %s: %s円 (利益%s円)", mark, site_name, f"{price:,}", f"{profit:+,}")

                                    if best_price is None or price < best_price:
                                        best_price = price
                                        best_site = site_name
                                else:
                                    log.info("  - %s: 価格なし", site_name)

                            except Exception as e:
                                log.info("  - %s: %s", site_name, e)
                            finally:
                                page.close()

                        if best_price is not None:
                            profit = kaitori - best_price - args.shipping
                            if profit >= args.threshold:
                                found_items.append({
                                    "JAN": jan, "商品名": row["商品名"],
                                    "最高買取価格": kaitori, "買取店": shop,
                                    "EC最安値": best_price, "ECサイト": best_site,
                                    "利益": profit,
                                })
                finally:
                    browser.close()

        except ImportError:
            log.error("Playwright がインストールされていません。pip install playwright && playwright install")
            sys.exit(1)

        # 結果サマリー
        log.info("=" * 60)
        if found_items:
            log.info("利益商品: %s件（閾値%s円以上）", len(found_items), f"{args.threshold:,}")
            for item in sorted(found_items, key=lambda x: x["利益"], reverse=True):
                log.info(
                    "  %+8s円 買取%8s円 EC%8s円 [%s] %s",
                    f"{item['利益']:,}", f"{item['最高買取価格']:,}",
                    f"{item['EC最安値']:,}", item["ECサイト"], item["商品名"][:35],
                )
        else:
            log.info("利益商品なし")
        log.info("=== 完了 ===")
        sys.exit(0)

    # CSV読み込み
    if args.csv:
        csv_path = Path(args.csv)
    else:
        csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
        if not csv_files:
            log.error("CSVファイルが見つかりません。")
            sys.exit(1)
        csv_path = csv_files[0]

    log.info("=== 利益商品自動抽出 開始 ===")
    log.info("ログファイル: %s", log_file)
    log.info("CSV: %s", csv_path.name)
    df = load_csv(str(csv_path))
    log.info("総商品数: %s", f"{len(df):,}")

    # 買取店フィルタ
    selected_shops = args.shops if args.shops is not None else list(SHOP_NAMES)
    if set(selected_shops) != set(SHOP_NAMES):
        shop_price_cols = [f"{s}_価格" for s in selected_shops if f"{s}_価格" in df.columns]
        if shop_price_cols:
            df["最高買取価格"] = df[shop_price_cols].max(axis=1)
            def best_shop(row):
                best_p, best_s = 0, ""
                for s in selected_shops:
                    col = f"{s}_価格"
                    if col in row.index and row[col] > best_p:
                        best_p = row[col]
                        best_s = s
                return best_s
            df["最高値店舗"] = df.apply(best_shop, axis=1)
            df = df[df["最高買取価格"] > 0]
    log.info("対象買取店: %s", ", ".join(selected_shops))

    # 買取価格下限フィルタ
    before_count = len(df)
    df = df[df["最高買取価格"] >= args.min_kaitori]
    skipped = before_count - len(df)
    if skipped > 0:
        log.info("買取価格 %s円未満をスキップ: %s件除外", f"{args.min_kaitori:,}", f"{skipped:,}")

    # 除外フィルタ（iPhone・中古・破損等）
    before_exclude = len(df)
    df = df[~df.apply(lambda r: is_excluded(r["商品名"], r.get("カテゴリ", "")), axis=1)]
    excluded = before_exclude - len(df)
    if excluded > 0:
        log.info("除外フィルタ: %s件除外（iPhone・中古・破損等）", f"{excluded:,}")

    # カテゴリフィルタ
    if args.categories and args.categories != ["all"]:
        before_cat = len(df)
        cat_keywords = args.categories

        def _matches_category(cat_str):
            cat_str = str(cat_str) if cat_str else ""
            return any(kw in cat_str for kw in cat_keywords)

        df = df[df["カテゴリ"].apply(_matches_category)]
        cat_filtered = before_cat - len(df)
        if cat_filtered > 0:
            log.info("カテゴリフィルタ: %s件除外 → %s件残（%s）",
                     f"{cat_filtered:,}", f"{len(df):,}", ", ".join(cat_keywords))
    else:
        log.info("カテゴリ: 全カテゴリ対象")

    # ソート
    sort_key = "利益候補スコア" if "利益候補スコア" in df.columns else "最高買取価格"

    # 検索対象の選定（モード別）
    jan_list = _select_targets(df, args, sort_key, log)
    target_rows = {row["JAN"]: row for _, row in df[df["JAN"].isin(jan_list)].iterrows()}
    # _select_targets が返した順序を保持（優先度順）
    target_rows = {jan: target_rows[jan] for jan in jan_list if jan in target_rows}
    jan_list = list(target_rows.keys())
    log.info("検索対象: %s件（%s モード）", len(jan_list), args.mode)
    log.info("現金利益閾値: %s円 / 送料: %s円", f"{args.threshold:,}", f"{args.shipping:,}")
    if args.pt_threshold > 0:
        log.info("PT込利益閾値: %s円", f"{args.pt_threshold:,}")
    log.info("楽天ボーナス: %s%% / Yahoo!ボーナス: %s%%", args.rakuten_bonus, args.yahoo_bonus)
    campaigns = get_active_campaigns()
    if campaigns:
        log.info("本日のキャンペーン: %s", ", ".join(campaigns))

    # キャッシュ
    if args.clear_cache:
        save_cache([])
        from ec_search import clear_ec_cache
        clear_ec_cache()
        log.info("キャッシュをクリアしました（利益結果 + EC検索）")

    cached = {r["JAN"]: r for r in load_cache_clean() if "JAN" in r}
    cached_jans = [j for j in jan_list if j in cached]
    uncached_jans = [j for j in jan_list if j not in cached]
    log.info("キャッシュ済み: %s件 / 新規検索: %s件", len(cached_jans), len(uncached_jans))

    # 結果リスト（キャッシュ分を先に追加）
    results = [cached[j] for j in cached_jans]
    _browser_opened = [0]

    # バッチ検索
    if uncached_jans:
        name_map = {jan: target_rows[jan]["商品名"] for jan in uncached_jans}
        # 利益判定は信頼買取価格（外れ値補正済み）ベース
        price_map = {jan: int(target_rows[jan].get("信頼買取価格") or target_rows[jan]["最高買取価格"])
                     for jan in uncached_jans}

        # Chrome拡張の自動巡回キューに即座に投入（API検索と並行して巡回開始）
        _queue_extension_crawl(uncached_jans, {}, log)

        start = time.time()
        mode = "APIのみ" if args.no_scraper else "API+スクレイパー"
        log.info("検索開始（2並列, %s）...", mode)

        # PT込閾値使用時はプリフィルタを緩くする（ポイント分を考慮）
        search_threshold = 0 if args.pt_threshold > 0 else args.threshold

        # ブラウザ即時オープン用
        _open_browser_limit = args.open_browser
        if _open_browser_limit > 0:
            import webbrowser as _wb
            _browser_sites = [s for s in args.ec_sites if s in EC_SEARCH_URLS]

        # 1件完了ごとに利益判定+キャッシュ保存+ブラウザオープン
        def _on_result(jan, ec):
            if not ec:
                return
            # 在庫切れでも利益商品は入荷待ちとしてキャッシュに残す
            row = target_rows[jan]
            max_kaitori = int(row["最高買取価格"])
            reliable_kaitori = int(row.get("信頼買取価格") or max_kaitori)
            is_outlier = bool(row.get("最高値_外れ値", False))
            # ★ハイブリッド: 利益判定は信頼価格ベース
            kaitori = reliable_kaitori
            pts = ec["points"] + bonus_points(ec["price"], ec["source"], args.rakuten_bonus, args.yahoo_bonus)
            coupon = ec.get("coupon", 0)
            # 送料無料商品はEC送料を0として扱う（買取発送料のみ）
            shipping = args.shipping
            if ec.get("free_shipping"):
                shipping = max(shipping - 500, 0)  # EC送料分を差し引く（概算500円）
            profit_info = calculate_cash_profit(kaitori, ec["price"], shipping, pts, coupon)

            if args.pt_threshold > 0:
                if profit_info["profit_with_points"] < args.pt_threshold:
                    return
            else:
                if not is_above_threshold(kaitori, ec["price"], args.threshold, shipping, coupon):
                    return

            stock = ec.get("stock_status", "unknown")
            upside_bonus = max_kaitori - reliable_kaitori
            # プレミア化判定
            msrp = ec.get("msrp") or 0
            is_premium = bool(msrp and max_kaitori > msrp)
            results.append({
                "JAN": jan,
                "商品名": row["商品名"],
                "最高買取価格": max_kaitori,
                "買取店": row["最高値店舗"],
                "信頼買取価格": reliable_kaitori,
                "上振れ余地": upside_bonus,
                "最高値_外れ値": is_outlier,
                # プレミア化シグナル
                "定価": int(msrp) if msrp else None,
                "プレミア化": is_premium,
                "買取_定価比": round(max_kaitori / msrp, 2) if msrp else None,
                "買取確認": row.get("買取確認", ""),
                "EC最安値": ec["price"],
                "EC店舗": ec["shop"],
                "ECソース": ec["source"],
                "EC URL": ec["url"],
                "ポイント": pts,
                "クーポン": coupon,
                "送料": shipping,
                "送料無料": ec.get("free_shipping", False),
                "現金利益": profit_info["cash_profit"],
                "PT込利益": profit_info["profit_with_points"],
                "ROI(%)": profit_info["roi"],
                # 上振れが実現した場合のベストケース利益
                "上振れ時利益": profit_info["cash_profit"] + upside_bonus,
                "stock_status": stock,
                "在庫状況": {
                    "in_stock": "在庫あり",
                    "limited": "残りわずか",
                    "out_of_stock": "在庫なし",
                }.get(stock, "未確認"),
                "商品リンク": ec["url"],
                "取得日時": datetime.now().strftime("%m/%d %H:%M"),
                # 収集経路マーカー
                "origin": "api" if ec.get("source") in ("楽天", "Yahoo") else "scraper",
            })
            save_cache_merge(results)
            upside_note = f" (上振れ+{upside_bonus:,}円まで期待可)" if upside_bonus > 0 else ""
            log.info(
                "利益発見: %s円 (PT込%s円) 買取%s円 EC%s円 [%s]%s %s",
                f"{profit_info['cash_profit']:+,}", f"{profit_info['profit_with_points']:+,}",
                f"{kaitori:,}", f"{ec['price']:,}", ec["source"], upside_note, row["商品名"][:35],
            )

            # 利益発見時に即座に確認済みEC URLだけをブラウザで開く
            if _open_browser_limit > 0 and _browser_opened[0] < _open_browser_limit:
                ec_url = ec.get("url", "")
                if ec_url:
                    _browser_opened[0] += 1
                    _wb.open(ec_url)
                    log.info("  → ブラウザで開きました [%d/%d] %s", _browser_opened[0], _open_browser_limit, ec["source"])

        ec_map = batch_search_ec_prices(
            uncached_jans,
            on_result=_on_result,
            product_names=name_map,
            kaitori_prices=price_map,
            threshold=search_threshold,
            shipping_cost=args.shipping,
            include_retailers=not args.no_scraper,
        )

        elapsed = time.time() - start
        found = sum(1 for v in ec_map.values() if v is not None)
        log.info("検索完了: %s秒 (%s/%s件 EC価格取得)", f"{elapsed:.0f}", found, len(uncached_jans))

    # キャッシュ保存（差分マージで Chrome拡張の同時書き込みを保護）
    save_cache_merge(results)

    # Chrome拡張の巡回完了を待つ（price_server経由でキュー投入済みの場合）
    if getattr(args, "wait_extension", False) and uncached_jans:
        from retailers import EXTENSION_ONLY_RETAILERS
        log.info("[拡張巡回待機] Chrome拡張が巡回を終えるまで待ちます...")
        _wait_crawl_completion(uncached_jans, EXTENSION_ONLY_RETAILERS, log,
                               timeout=getattr(args, "extension_timeout", 300))
        # 待機後にキャッシュを再読み込みして結果を更新
        refreshed = load_cache()
        refreshed_map = {r["JAN"]: r for r in refreshed}
        results = [refreshed_map.get(r["JAN"], r) for r in results]
        # 新たにキャッシュに加わったJANも取り込む
        for r in refreshed:
            if not any(x["JAN"] == r["JAN"] for x in results):
                results.append(r)

    # 結果表示
    all_profitable = [r for r in results if r.get("現金利益", 0) > 0]

    log.info("=" * 60)
    log.info("利益商品: %s件", len(all_profitable))
    if all_profitable:
        sorted_results = sorted(all_profitable, key=lambda x: x.get("PT込利益", 0), reverse=True)
        for r in sorted_results[:20]:
            log.info(
                "  %+8s円 (PT込%+8s円) 買取%8s円 EC%8s円 [%s] %s",
                f"{r['現金利益']:,}", f"{r['PT込利益']:,}",
                f"{r['最高買取価格']:,}", f"{r['EC最安値']:,}",
                r["ECソース"], r["商品名"][:35],
            )
        if len(sorted_results) > 20:
            log.info("  ... 他%s件", len(sorted_results) - 20)
    # PT込黒字の表示
    pt_profitable = [r for r in results if r.get("PT込利益", 0) > 0]
    if len(pt_profitable) > len(all_profitable):
        log.info("PT込黒字: %s件（現金赤字だがポイント込みで黒字）", len(pt_profitable) - len(all_profitable))

    # ヒット率と次のアクション提案
    searched_total = len(uncached_jans) + len(cached_jans) if uncached_jans else len(cached_jans)
    hit_rate = len(all_profitable) / searched_total * 100 if searched_total > 0 else 0
    log.info("ヒット率: %s/%s件 (%.1f%%)", len(all_profitable), searched_total, hit_rate)

    if len(all_profitable) == 0:
        log.info("")
        log.info("=== 利益商品が見つからない場合の対策 ===")
        log.info("  1. 閾値を下げる: --threshold 0 --pt-threshold 2000")
        log.info("  2. 検索範囲を広げる: --top 500")
        log.info("  3. 買取価格下限を下げる: --min-kaitori 3000")
        log.info("  4. キャンペーン日に再実行: 楽天マラソン中・5のつく日はPT還元増")
        log.info("  5. 分析ツール: python analyze.py --shop-gap（価格差の大きい商品を確認）")

    log.info("結果は %s に保存済み", CACHE_FILE.name)
    log.info("ログファイル: %s", log_file)

    # ブラウザで確認済みEC URLを開く（キャッシュ済み分。検索中に見つかった分は既に開済み）
    if args.open_browser > 0 and cached_jans and all_profitable:
        import webbrowser

        already_opened = _browser_opened[0] if uncached_jans else 0
        remaining = args.open_browser - already_opened
        if remaining > 0:
            sorted_for_browser = sorted(all_profitable, key=lambda x: x.get("PT込利益", 0), reverse=True)
            cached_jan_set = set(cached_jans)
            cached_profitable = [r for r in sorted_for_browser if r["JAN"] in cached_jan_set and r.get("商品リンク")]
            open_count = min(remaining, len(cached_profitable))

            if open_count > 0:
                log.info("キャッシュ済み利益商品 %s件の確認済みEC URLを開きます...", open_count)
                for item in cached_profitable[:open_count]:
                    webbrowser.open(item["商品リンク"])
                    time.sleep(random.uniform(0.2, 0.6))

    log.info("=== 完了 ===")


if __name__ == "__main__":
    main()
