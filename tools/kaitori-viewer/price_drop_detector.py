"""価格下落検知モジュール（戦略C）

~/.kaitori-viewer/price_history.json から、EC価格が過去最高値から下落した
JANを抽出し、優先的に再検索対象とする。

使い方:
    from price_drop_detector import detect_price_drops
    drop_jans = detect_price_drops(min_drop_pct=10.0)

    # 単体テスト
    python price_drop_detector.py
"""

import json
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


def detect_price_drops(
    min_drop_pct: float = 10.0,
    lookback_days: int = 30,
) -> list[tuple[str, float]]:
    """価格が下落したJANを下落率の降順で返す。

    Args:
        min_drop_pct: 最低下落率（%）。これ未満は対象外
        lookback_days: 過去何日の履歴を見るか

    Returns:
        [(jan, drop_pct), ...] 下落率の大きい順
    """
    history = _load_history()
    if not history:
        return []

    cutoff = datetime.now() - timedelta(days=lookback_days)
    results: list[tuple[str, float]] = []

    for jan, entries in history.items():
        if not isinstance(entries, list) or len(entries) < 2:
            continue  # 履歴が2件未満は下落判定不能

        # 期間内のエントリのみ抽出
        valid = []
        for e in entries:
            if not isinstance(e, dict) or "price" not in e or "date" not in e:
                continue
            try:
                dt = datetime.fromisoformat(e["date"])
                if dt >= cutoff:
                    valid.append({"price": int(e["price"]), "dt": dt})
            except (ValueError, TypeError):
                continue

        if len(valid) < 2:
            continue

        # 最高値と最新価格を比較
        max_price = max(v["price"] for v in valid)
        latest = max(valid, key=lambda v: v["dt"])
        latest_price = latest["price"]

        if max_price <= 0 or latest_price >= max_price:
            continue

        drop_pct = (max_price - latest_price) / max_price * 100
        if drop_pct >= min_drop_pct:
            results.append((jan, drop_pct))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


if __name__ == "__main__":
    drops = detect_price_drops(min_drop_pct=10.0)
    print(f"=== 価格下落検知 ===")
    print(f"検出数: {len(drops)}件")
    for jan, pct in drops[:20]:
        print(f"  {jan}: -{pct:.1f}%")
    if not drops:
        print("価格下落商品なし（履歴が蓄積されるまで時間がかかります）")
