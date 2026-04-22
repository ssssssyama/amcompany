"""ヤフオク落札相場スクレイパー（戦略J）

JANリストのヤフオク過去落札中央値を並列取得し、
~/.kaitori-viewer/auction_history.json に蓄積。

使い方:
    python yauc_scraper.py --top 30
    python yauc_scraper.py --jans 4549292167382
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

_HISTORY_FILE = Path.home() / ".kaitori-viewer" / "auction_history.json"
_WORKER_PATH = Path(__file__).parent / "_yauc_worker.py"
_MAX_WORKERS = 1  # ヤフオクbot対策のため1並列に制限
_TIMEOUT = 30


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


def _fetch_one(jan: str) -> dict | None:
    try:
        result = subprocess.run(
            [sys.executable, str(_WORKER_PATH), jan],
            capture_output=True, text=True, timeout=_TIMEOUT, encoding="utf-8",
        )
        if result.returncode != 0:
            return None
        line = result.stdout.strip().split("\n")[-1]
        data = json.loads(line)
        if data.get("error") or data.get("median") is None:
            return None
        return data
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, OSError):
        return None


def scrape_auction_medians(jan_list: list[str]) -> dict[str, int]:
    """JANリストの落札中央値を取得し、履歴に追記する。

    Returns:
        {jan: median_price} のマップ
    """
    history = _load_history()
    now = datetime.now().isoformat(timespec="seconds")
    results: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        futures = {ex.submit(_fetch_one, jan): jan for jan in jan_list}
        for fut in as_completed(futures):
            jan = futures[fut]
            data = fut.result()
            if not data:
                logger.warning("%s: 取得失敗", jan)
                continue

            median = data["median"]
            count = data.get("count", 0)
            results[jan] = median
            history.setdefault(jan, []).append({
                "median": median, "count": count, "date": now,
            })
            history[jan] = history[jan][-30:]
            logger.info("%s: 中央値%s円 (%d件)", jan, f"{median:,}", count)

    _save_history(history)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="ヤフオク落札相場スクレイパー")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--jans", nargs="*")
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
    scrape_auction_medians(target_jans)
