"""メルカリ出品密度急増検知（戦略M）

~/.kaitori-viewer/mercari_history.json から、出品数が過去平均の 1.5 倍以上に
増加したJANを抽出する。転売業者が動き出したシグナル。

使い方:
    from mercari_density_detector import detect_density_spikes
    spikes = detect_density_spikes(min_increase_pct=50.0)

    # 単体テスト
    python mercari_density_detector.py
"""

import json
from pathlib import Path

_HISTORY_FILE = Path.home() / ".kaitori-viewer" / "mercari_history.json"


def _load_history() -> dict:
    if not _HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def detect_density_spikes(
    min_increase_pct: float = 50.0,
    min_samples: int = 3,
    min_count: int = 3,
) -> list[tuple[str, int, float]]:
    """過去の平均出品数から `min_increase_pct` 以上増えたJANを返す。

    Args:
        min_increase_pct: 増加率（%）の閾値
        min_samples: 履歴最低件数（これ未満は判定不能）
        min_count: 最新出品数の最低値（0件や1件のノイズ排除）

    Returns:
        [(jan, current_count, increase_pct), ...] 増加率の大きい順
    """
    history = _load_history()
    if not history:
        return []

    results: list[tuple[str, int, float]] = []
    for jan, entries in history.items():
        if not isinstance(entries, list) or len(entries) < min_samples:
            continue
        valid = [e for e in entries if isinstance(e, dict) and isinstance(e.get("count"), int) and e["count"] >= 0]
        if len(valid) < min_samples:
            continue

        latest = valid[-1]["count"]
        if latest < min_count:
            continue

        # 最新を除いた過去の平均
        past = [e["count"] for e in valid[:-1]]
        avg = sum(past) / len(past)
        if avg <= 0:
            continue

        increase_pct = (latest - avg) / avg * 100
        if increase_pct >= min_increase_pct:
            results.append((jan, latest, increase_pct))

    results.sort(key=lambda x: x[2], reverse=True)
    return results


if __name__ == "__main__":
    spikes = detect_density_spikes(min_increase_pct=50.0)
    print(f"=== メルカリ出品密度急増検知 ===")
    print(f"検出数: {len(spikes)}件")
    for jan, count, pct in spikes[:20]:
        print(f"  {jan}: 現在{count}件 (+{pct:.1f}%)")
    if not spikes:
        print("急増なし（mercari_scraper.py で履歴を蓄積してください）")
