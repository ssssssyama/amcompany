"""メルカリ出品数スクレイパー（戦略M）

JANごとのメルカリ出品数を収集し、~/.kaitori-viewer/mercari_history.json に履歴を蓄積する。
後段の mercari_density_detector.py で出品数急増を検知する。

使い方:
    # CSVスコア上位200件の出品数を収集
    python mercari_scraper.py --top 200

    # 特定のJANリストだけ
    python mercari_scraper.py --jans 4549292167382 4512345678901
"""

import argparse
import json
import logging
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_HISTORY_FILE = Path.home() / ".kaitori-viewer" / "mercari_history.json"
_WORKER_PATH = Path(__file__).parent / "_mercari_worker.py"
_MAX_WORKERS = 2  # Playwright並列数（メモリ保護）
_TIMEOUT = 30  # 1JANあたりの最大秒数


def _load_history() -> dict:
    if not _HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_history(history: dict) -> None:
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")


def _fetch_one(jan: str) -> int:
    """サブプロセスで1JANのメルカリ出品数を取得"""
    try:
        result = subprocess.run(
            [sys.executable, str(_WORKER_PATH), jan],
            capture_output=True, text=True, timeout=_TIMEOUT, encoding="utf-8",
        )
        if result.returncode != 0:
            return -1
        data = json.loads(result.stdout.strip().split("\n")[-1])
        return int(data.get("count", -1))
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, OSError):
        return -1


def scrape_counts(jan_list: list[str]) -> dict[str, int]:
    """JANリストの出品数を並列取得し、履歴に追記する。

    Returns:
        {jan: count} のマップ
    """
    history = _load_history()
    now = datetime.now().isoformat(timespec="seconds")
    results: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        futures = {ex.submit(_fetch_one, jan): jan for jan in jan_list}
        for fut in as_completed(futures):
            jan = futures[fut]
            count = fut.result()
            results[jan] = count
            if count < 0:
                logger.warning("%s: 取得失敗", jan)
                continue

            history.setdefault(jan, []).append({"count": count, "date": now})
            # 古いエントリを30件まで保持
            history[jan] = history[jan][-30:]
            logger.info("%s: %d件", jan, count)

    _save_history(history)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="メルカリ出品数スクレイパー")
    parser.add_argument("--top", type=int, default=50,
                        help="CSVスコア上位N件を対象")
    parser.add_argument("--jans", nargs="*", help="特定のJANコードのみ対象")
    args = parser.parse_args()

    if args.jans:
        target_jans = args.jans
    else:
        from csv_loader import load_csv
        CSV_DIR = Path(__file__).resolve().parent.parent.parent
        csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
        if not csv_files:
            print("CSVなし")
            sys.exit(1)
        df = load_csv(str(csv_files[0]))
        target_jans = df.sort_values("利益候補スコア", ascending=False).head(args.top)["JAN"].tolist()

    logger.info("対象: %d件", len(target_jans))
    results = scrape_counts(target_jans)
    got = sum(1 for c in results.values() if c >= 0)
    logger.info("取得成功: %d/%d件", got, len(results))
