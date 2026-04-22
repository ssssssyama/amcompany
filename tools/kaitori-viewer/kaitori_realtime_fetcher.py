"""買取価格のリアルタイム取得モジュール

CSV は定期更新（数日～数週間）だが、買取店は頻繁に価格改定する。
主要JANの買取確認URLを実スクレイピングし、CSV価格との差分を検出する。

使い方:
    from kaitori_realtime_fetcher import fetch_realtime_prices, detect_kaitori_updates

    # 上位 100 JAN の買取価格を更新取得（キャッシュに保存）
    updates = fetch_realtime_prices(top_n=100)

    # CSV価格より上昇したJANを取得（戦略Eの強化版）
    upgrades = detect_kaitori_updates(min_increase_pct=3.0)

単体実行:
    python kaitori_realtime_fetcher.py --top 100
"""

import argparse
import json
import logging
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_HISTORY_FILE = Path.home() / ".kaitori-viewer" / "kaitori_realtime.json"
_WORKER_PATH = Path(__file__).parent / "_kaitori_price_worker.py"
_MAX_WORKERS = 2  # 買取店への同時アクセス制限
_TIMEOUT = 30


def _load_history() -> dict:
    if not _HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_history(data: dict) -> None:
    _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HISTORY_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _fetch_one(jan: str, url: str) -> int | None:
    """サブプロセスで1 JAN の買取価格を取得"""
    if not url:
        return None
    try:
        result = subprocess.run(
            [sys.executable, str(_WORKER_PATH), jan, url],
            capture_output=True, text=True, timeout=_TIMEOUT, encoding="utf-8",
        )
        if result.returncode != 0:
            return None
        line = result.stdout.strip().split("\n")[-1]
        if line == "null":
            return None
        data = json.loads(line)
        return int(data.get("price", 0)) or None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, OSError):
        return None


def fetch_realtime_prices(
    top_n: int = 100,
    min_kaitori: int = 5000,
) -> dict[str, dict]:
    """CSV スコア上位の買取価格をリアルタイムで再取得する。

    Args:
        top_n: 対象JAN数（スコア上位）
        min_kaitori: 買取価格下限（ノイズ商品を排除）

    Returns:
        {jan: {"price": int, "csv_price": int, "delta_pct": float, "date": iso}}
    """
    from csv_loader import load_csv
    csv_dir = Path(__file__).resolve().parent.parent.parent
    csv_files = sorted(csv_dir.glob("all_data_*.csv"), reverse=True)
    if not csv_files:
        logger.warning("CSVなし")
        return {}
    df = load_csv(str(csv_files[0]))
    df = df[df["最高買取価格"] >= min_kaitori]
    sort_key = "利益候補スコア" if "利益候補スコア" in df.columns else "最高買取価格"
    targets = df.sort_values(sort_key, ascending=False).head(top_n)

    history = _load_history()
    now = datetime.now().isoformat(timespec="seconds")
    results: dict[str, dict] = {}

    def _task(jan, url, csv_price):
        rt_price = _fetch_one(jan, url)
        if not rt_price:
            return None
        delta = (rt_price - csv_price) / csv_price * 100 if csv_price else 0.0
        return {"jan": jan, "rt_price": rt_price, "csv_price": csv_price, "delta": delta}

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        futures = []
        for _, row in targets.iterrows():
            jan = row["JAN"]
            url = row.get("買取確認", "")
            csv_price = int(row["最高買取価格"])
            if url:
                futures.append(ex.submit(_task, jan, url, csv_price))
        for fut in as_completed(futures):
            data = fut.result()
            if not data:
                continue
            jan = data["jan"]
            results[jan] = {
                "price": data["rt_price"],
                "csv_price": data["csv_price"],
                "delta_pct": round(data["delta"], 2),
                "date": now,
            }
            # 履歴にも追記
            history.setdefault(jan, []).append({
                "price": data["rt_price"],
                "date": now,
            })
            history[jan] = history[jan][-30:]  # 最新30件のみ保持
            if abs(data["delta"]) >= 3.0:
                sign = "+" if data["delta"] > 0 else ""
                logger.info("買取変動: %s %s円→%s円 (%s%.1f%%)",
                            jan, f"{data['csv_price']:,}", f"{data['rt_price']:,}",
                            sign, data["delta"])

    _save_history(history)
    return results


def detect_kaitori_updates(min_increase_pct: float = 3.0) -> list[tuple[str, float]]:
    """直近のリアルタイム取得データから買取価格が上昇したJANを返す。

    戦略E（買取価格上昇）の強化版。スナップショット日次よりも細かい粒度で検出。

    Returns:
        [(jan, increase_pct), ...] 上昇率の大きい順
    """
    history = _load_history()
    results: list[tuple[str, float]] = []
    for jan, entries in history.items():
        if not isinstance(entries, list) or len(entries) < 2:
            continue
        latest = entries[-1].get("price", 0)
        # 過去10件の最小値を比較基準に（一時変動ではなく安定した上昇を検知）
        prev_prices = [e.get("price", 0) for e in entries[-10:-1] if e.get("price")]
        if not prev_prices or latest <= 0:
            continue
        base = min(prev_prices)
        if base <= 0:
            continue
        pct = (latest - base) / base * 100
        if pct >= min_increase_pct:
            results.append((jan, pct))
    return sorted(results, key=lambda x: x[1], reverse=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="買取価格リアルタイム取得")
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--min-kaitori", type=int, default=5000)
    args = parser.parse_args()

    print(f"買取価格リアルタイム取得: 上位{args.top}JAN...")
    results = fetch_realtime_prices(args.top, args.min_kaitori)
    print(f"\n取得完了: {len(results)}件")
    # 変動上位10件
    sorted_results = sorted(results.items(), key=lambda x: abs(x[1]["delta_pct"]), reverse=True)
    print("\n=== 変動率上位 ===")
    for jan, d in sorted_results[:10]:
        sign = "+" if d["delta_pct"] > 0 else ""
        print(f"  {jan}: {d['csv_price']:,}→{d['rt_price']:,}円 ({sign}{d['delta_pct']:.1f}%)")

    print("\n=== 上昇検知（直近10回比）===")
    ups = detect_kaitori_updates(min_increase_pct=3.0)
    print(f"{len(ups)}件")
    for jan, pct in ups[:10]:
        print(f"  {jan}: +{pct:.1f}%")
