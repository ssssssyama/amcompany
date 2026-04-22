"""EC価格異常値検知（戦略P）

~/.kaitori-viewer/price_history.json から、現在価格が過去30日中央値の
40%以下になったJANを抽出する。業者の値付けミスや出血サービス価格の
即決利益候補。

使い方:
    from price_anomaly_detector import detect_price_anomalies
    anomalies = detect_price_anomalies(threshold_pct=40.0)

    # 単体テスト
    python price_anomaly_detector.py
"""

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path

_PRICE_HISTORY_FILE = Path.home() / ".kaitori-viewer" / "price_history.json"


def _load_history() -> dict:
    if not _PRICE_HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(_PRICE_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def detect_price_anomalies(
    threshold_pct: float = 40.0,
    lookback_days: int = 30,
    min_samples: int = 3,
) -> list[tuple[str, int, int, float]]:
    """現在価格が過去中央値の threshold_pct 以下になったJANを返す。

    Args:
        threshold_pct: この割合（%）以下で異常判定
        lookback_days: 過去何日の履歴を中央値計算に使うか
        min_samples: 中央値計算に必要な最低サンプル数

    Returns:
        [(jan, current_price, median_price, ratio_pct), ...] 割安度の大きい順
    """
    history = _load_history()
    if not history:
        return []

    cutoff = datetime.now() - timedelta(days=lookback_days)
    results: list[tuple[str, int, int, float]] = []

    for jan, entries in history.items():
        if not isinstance(entries, list) or len(entries) < min_samples:
            continue

        valid: list[dict] = []
        for e in entries:
            if not isinstance(e, dict) or "price" not in e or "date" not in e:
                continue
            try:
                dt = datetime.fromisoformat(e["date"])
                price = int(e["price"])
            except (ValueError, TypeError):
                continue
            if price > 0 and dt >= cutoff:
                valid.append({"price": price, "dt": dt})

        if len(valid) < min_samples:
            continue

        # 最新価格 vs 過去中央値（最新は除外して比較の汚染を防ぐ）
        latest = max(valid, key=lambda v: v["dt"])
        historical = [v["price"] for v in valid if v["dt"] < latest["dt"]]
        if len(historical) < min_samples - 1:
            continue

        median_price = int(statistics.median(historical))
        if median_price <= 0:
            continue

        ratio_pct = latest["price"] / median_price * 100
        if ratio_pct <= threshold_pct:
            results.append((jan, latest["price"], median_price, ratio_pct))

    # 割安度の大きい順（ratio_pct が小さい = より異常）
    results.sort(key=lambda x: x[3])
    return results


if __name__ == "__main__":
    anomalies = detect_price_anomalies(threshold_pct=40.0)
    print(f"=== 価格異常値検知 ===")
    print(f"検出数: {len(anomalies)}件")
    for jan, cur, median, ratio in anomalies[:20]:
        print(f"  {jan}: 現在{cur:,}円 / 中央値{median:,}円 ({ratio:.1f}%)")
    if not anomalies:
        print("異常値なし（履歴が十分蓄積されるまで時間がかかります）")
