"""在庫復活監視ループ（戦略G の定期実行版）

cache_results.json から過去利益JANで在庫切れのものを抽出し、
N分ごとに EC を再検索。在庫復活を検知したら notifier で通知。

使い方:
    # 15分間隔で常時監視
    python restock_watcher.py

    # 5分間隔、1時間で終了
    python restock_watcher.py --interval 5 --duration 60

    # 特定JANのみ
    python restock_watcher.py --jans 4549292167382 4710483948589
"""

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_SHUTDOWN = False


def _handle_signal(signum, frame):
    global _SHUTDOWN
    _SHUTDOWN = True
    logger.info("[watcher] 終了シグナル受信。次のサイクル完了後に停止します")


signal.signal(signal.SIGINT, _handle_signal)
if sys.platform != "win32":
    signal.signal(signal.SIGTERM, _handle_signal)


def _load_results_cache() -> list:
    f = Path.home() / ".kaitori-viewer" / "cache_results.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_results_cache(data: list) -> None:
    f = Path.home() / ".kaitori-viewer" / "cache_results.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _get_target_jans(custom_jans: list[str] | None, min_profit: int = 1000) -> list[dict]:
    """監視対象を返す（過去利益JANで在庫切れのもの）"""
    if custom_jans:
        return [{"JAN": j, "商品名": "", "現金利益": 0, "EC URL": ""} for j in custom_jans]

    cache = _load_results_cache()
    targets = []
    for r in cache:
        if not isinstance(r, dict):
            continue
        profit = r.get("現金利益", 0)
        stock = r.get("在庫状況", "")
        if profit > min_profit and stock in ("在庫なし", "残りわずか", "未確認"):
            targets.append(r)
    return targets


def _check_and_notify(targets: list[dict]) -> int:
    """各JANをEC再検索、復活したものに通知。復活件数を返す"""
    from ec_search import search_best_ec_price, _clear_ec_cache_for_jan, _set_ec_cache
    from notifier import notify_restock

    restocked = 0
    for target in targets:
        if _SHUTDOWN:
            break
        jan = target.get("JAN", "")
        name = target.get("商品名", "")
        kaitori = int(target.get("最高買取価格", 0) or 0)
        if not jan:
            continue

        # キャッシュを無視して強制再検索（最新状態）
        try:
            # キャッシュクリアヘルパーがない場合は _set_ec_cache を直接使う
            try:
                from ec_search import _ec_cache, _ec_cache_lock
                with _ec_cache_lock:
                    _ec_cache.pop(jan, None)
            except Exception:
                pass

            result = search_best_ec_price(
                jan,
                include_retailers=False,  # API 優先（早く、軽量）
                product_name=name,
                kaitori_price=kaitori,
            )
        except Exception as e:
            logger.debug("[watcher] 検索失敗 %s: %s", jan, e)
            continue

        if not result:
            continue
        stock = result.get("stock_status", "")
        if stock != "in_stock":
            continue

        # 復活検知
        price = result.get("price", 0)
        url = result.get("url", "")
        logger.info("[watcher] 🎉 復活: %s %s円 %s", jan, f"{price:,}", name[:40])
        notify_restock(jan=jan, name=name, price=price, url=url)
        restocked += 1

        # cache_results の該当エントリを更新（在庫状況を in_stock に）
        cache = _load_results_cache()
        for r in cache:
            if isinstance(r, dict) and r.get("JAN") == jan:
                r["在庫状況"] = "在庫あり"
                r["EC最安値"] = price
                r["EC URL"] = url
                break
        _save_results_cache(cache)

    return restocked


def run_watcher(interval_minutes: int, duration_minutes: int | None, custom_jans: list[str] | None):
    """監視ループ"""
    logger.info("[watcher] 開始: interval=%d分 duration=%s 対象=%s",
                interval_minutes, f"{duration_minutes}分" if duration_minutes else "無期限",
                custom_jans if custom_jans else "cache_results 自動")

    start = time.time()
    cycle = 0
    while not _SHUTDOWN:
        cycle += 1
        targets = _get_target_jans(custom_jans)
        if not targets:
            logger.info("[watcher] cycle %d: 監視対象0件。次のサイクルまで待機", cycle)
        else:
            logger.info("[watcher] cycle %d: %d件を再チェック", cycle, len(targets))
            restocked = _check_and_notify(targets)
            if restocked:
                logger.info("[watcher] cycle %d: %d件が復活", cycle, restocked)

        # 終了時刻チェック
        if duration_minutes and (time.time() - start) >= duration_minutes * 60:
            logger.info("[watcher] duration経過で終了")
            break

        # インターバル待機
        for _ in range(interval_minutes * 60):
            if _SHUTDOWN:
                break
            time.sleep(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    parser = argparse.ArgumentParser(description="在庫復活監視ループ（戦略G拡張）")
    parser.add_argument("--interval", type=int, default=15, help="監視間隔（分、デフォルト15）")
    parser.add_argument("--duration", type=int, default=None, help="総監視時間（分、省略時は無期限）")
    parser.add_argument("--jans", nargs="*", help="特定JANのみ監視（省略時は cache_results 自動）")
    args = parser.parse_args()
    run_watcher(args.interval, args.duration, args.jans)
