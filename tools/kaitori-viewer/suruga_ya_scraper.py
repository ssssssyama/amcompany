"""駿河屋スクレイパー（戦略R）

JANリストの駿河屋価格を並列取得し、~/.kaitori-viewer/secondhand_history.json に蓄積。
レトロゲーム/トレカ/フィギュア等の中古実勢価格を追跡。

使い方:
    python suruga_ya_scraper.py --top 50            # CSVスコア上位
    python suruga_ya_scraper.py --jans 4901111ABCDE
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

_HISTORY_FILE = Path.home() / ".kaitori-viewer" / "secondhand_history.json"
_WORKER_PATH = Path(__file__).parent / "_suruga_ya_worker.py"
_MAX_WORKERS = 2
_TIMEOUT = 30

# 駿河屋の主要取扱カテゴリ
_TARGET_CATEGORIES = [
    "ゲーム", "トレーディングカード", "トレカ", "フィギュア",
    "プラモデル", "ホビー", "Blu-ray", "DVD", "CD", "本", "コミック",
]


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
    """サブプロセスで駿河屋価格を取得"""
    try:
        result = subprocess.run(
            [sys.executable, str(_WORKER_PATH), jan],
            capture_output=True, text=True, timeout=_TIMEOUT, encoding="utf-8",
        )
        if result.returncode != 0:
            return None
        line = result.stdout.strip().split("\n")[-1]
        data = json.loads(line)
        if data.get("error"):
            return None
        if data.get("new_price") is None and data.get("used_price") is None:
            return None
        return data
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, OSError):
        return None


def is_target_category(category: str) -> bool:
    """駿河屋取扱カテゴリかを判定"""
    if not category:
        return False
    return any(c in category for c in _TARGET_CATEGORIES)


def scrape_suruga_ya(jan_list: list[str]) -> dict[str, dict]:
    """JANリストの駿河屋価格を取得し、履歴に追記する。

    Returns:
        {jan: {new_price, used_price}} のマップ
    """
    history = _load_history()
    now = datetime.now().isoformat(timespec="seconds")
    results: dict[str, dict] = {}

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        futures = {ex.submit(_fetch_one, jan): jan for jan in jan_list}
        for fut in as_completed(futures):
            jan = futures[fut]
            data = fut.result()
            if not data:
                logger.warning("%s: 取得失敗", jan)
                continue
            results[jan] = data
            history.setdefault(jan, []).append({
                "new_price": data.get("new_price"),
                "used_price": data.get("used_price"),
                "date": now,
            })
            history[jan] = history[jan][-30:]
            logger.info("%s: 新%s 中古%s",
                        jan,
                        f"{data.get('new_price'):,}円" if data.get('new_price') else "-",
                        f"{data.get('used_price'):,}円" if data.get('used_price') else "-")

    _save_history(history)
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="駿河屋スクレイパー")
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
        # 駿河屋カテゴリのみ対象
        df_target = df[df["カテゴリ"].apply(is_target_category)]
        logger.info("駿河屋対象カテゴリ: %d件 / %d件", len(df_target), len(df))
        target_jans = df_target.sort_values("利益候補スコア", ascending=False).head(args.top)["JAN"].tolist()

    logger.info("対象: %d件", len(target_jans))
    scrape_suruga_ya(target_jans)
