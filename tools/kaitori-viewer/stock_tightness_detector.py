"""在庫切迫検知（戦略K）

ec_cache.json から商品名に「残り3点」等の在庫数表示が含まれるJANを抽出。
在庫切迫＝価格上昇直前のシグナル。

使い方:
    from stock_tightness_detector import detect_stock_tightness
    jans = detect_stock_tightness(max_stock=3)

    # 単体テスト
    python stock_tightness_detector.py
"""

import json
from pathlib import Path

_EC_CACHE_FILE = Path.home() / ".kaitori-viewer" / "ec_cache.json"


def _load_cache() -> dict:
    if not _EC_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_EC_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def detect_stock_tightness(max_stock: int = 3) -> list[tuple[str, int]]:
    """在庫数が max_stock 以下のJANを返す（少ない順）。

    Args:
        max_stock: この数以下を切迫とみなす

    Returns:
        [(jan, stock_count), ...] 在庫数の少ない順
    """
    cache = _load_cache()
    results: list[tuple[str, int]] = []
    for jan, entry in cache.items():
        if not isinstance(entry, dict):
            continue
        stock = entry.get("stock_count")
        if isinstance(stock, int) and 1 <= stock <= max_stock:
            results.append((jan, stock))
    return sorted(results, key=lambda x: x[1])


if __name__ == "__main__":
    tight = detect_stock_tightness(max_stock=3)
    print(f"=== 在庫切迫検知 ===")
    print(f"検出数: {len(tight)}件")
    for jan, count in tight[:20]:
        print(f"  {jan}: 在庫{count}点")
    if not tight:
        print("該当なし（ec_cache.json に在庫数表示付き商品が記録されてから検出されます）")
