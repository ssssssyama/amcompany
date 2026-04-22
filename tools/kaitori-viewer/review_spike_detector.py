"""レビュー数ジャンプ検知（戦略N）

ec_cache.json から review_count スナップショットを蓄積し、
過去比 +10件以上の急増JANを検出する。バズ商品の早期発見。

使い方:
    from review_spike_detector import save_review_snapshot, detect_review_spikes
    save_review_snapshot()         # auto_extract 実行毎に呼ぶ
    spikes = detect_review_spikes(min_increase=10)

    # 単体テスト
    python review_spike_detector.py
"""

import json
from datetime import datetime
from pathlib import Path

_EC_CACHE_FILE = Path.home() / ".kaitori-viewer" / "ec_cache.json"
_HISTORY_FILE = Path.home() / ".kaitori-viewer" / "review_history.json"
_MAX_PER_JAN = 30  # JANごとの履歴保持上限


def _load_ec_cache() -> dict:
    if not _EC_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_EC_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


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


def save_review_snapshot() -> int:
    """ec_cache.json から review_count を抽出して履歴に追記。

    Returns:
        追記したJAN数
    """
    cache = _load_ec_cache()
    if not cache:
        return 0

    history = _load_history()
    now = datetime.now().isoformat(timespec="seconds")
    added = 0

    for jan, entry in cache.items():
        if not isinstance(entry, dict):
            continue
        review_count = entry.get("review_count")
        if not isinstance(review_count, int) or review_count <= 0:
            continue
        history.setdefault(jan, []).append({"count": review_count, "date": now})
        history[jan] = history[jan][-_MAX_PER_JAN:]
        added += 1

    _save_history(history)
    return added


def detect_review_spikes(min_increase: int = 10, min_samples: int = 2) -> list[tuple[str, int, int]]:
    """レビュー数が前回比 min_increase 以上のJANを返す。

    Args:
        min_increase: 増加件数の閾値
        min_samples: 履歴最低件数

    Returns:
        [(jan, current_count, increase), ...] 増加数の大きい順
    """
    history = _load_history()
    if not history:
        return []

    results: list[tuple[str, int, int]] = []
    for jan, entries in history.items():
        if not isinstance(entries, list) or len(entries) < min_samples:
            continue
        valid = [e for e in entries if isinstance(e, dict) and isinstance(e.get("count"), int)]
        if len(valid) < min_samples:
            continue

        current = valid[-1]["count"]
        prev = valid[0]["count"]  # 最古との比較で長期トレンドを捉える
        increase = current - prev
        if increase >= min_increase:
            results.append((jan, current, increase))

    results.sort(key=lambda x: x[2], reverse=True)
    return results


if __name__ == "__main__":
    added = save_review_snapshot()
    print(f"レビュースナップショット保存: {added}件")

    spikes = detect_review_spikes(min_increase=10)
    print(f"\n=== レビュー数ジャンプ検知 ===")
    print(f"検出数: {len(spikes)}件")
    for jan, cur, inc in spikes[:20]:
        print(f"  {jan}: {cur}件 (+{inc})")
    if not spikes:
        print("急増なし（履歴が蓄積されるまで時間がかかります）")
