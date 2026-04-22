"""在庫切れ復活監視（戦略G）

過去に利益が出たJANで現在在庫切れのものを抽出し、
auto_extract の優先検索対象にする。在庫が復活した瞬間を逃さないため。

使い方:
    from restock_monitor import get_restock_candidates
    jans = get_restock_candidates(min_profit=1000)

    # 単体テスト
    python restock_monitor.py
"""

import json
from pathlib import Path

_CACHE_FILE = Path.home() / ".kaitori-viewer" / "cache_results.json"

# 在庫切れ判定キーワード（auto_extract.py の在庫状況マッピングと整合）
_OUT_OF_STOCK_LABELS = ("在庫なし", "残りわずか")


def get_restock_candidates(min_profit: int = 0) -> list[str]:
    """過去利益JANで現在在庫切れのものを利益額降順で返す。

    Args:
        min_profit: この利益額（円）を超えたもののみ対象。0=全て

    Returns:
        JANコードのリスト（利益額降順）
    """
    if not _CACHE_FILE.exists():
        return []

    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    candidates: list[tuple[str, int]] = []
    for r in data:
        if not isinstance(r, dict):
            continue
        jan = str(r.get("JAN", "")).strip()
        if not jan:
            continue
        profit = r.get("現金利益", 0)
        if not isinstance(profit, (int, float)) or profit <= min_profit:
            continue
        stock = r.get("在庫状況", "")
        if stock in _OUT_OF_STOCK_LABELS:
            candidates.append((jan, int(profit)))

    # 重複JAN除去（最大利益額を採用）
    seen: dict[str, int] = {}
    for jan, profit in candidates:
        if jan not in seen or profit > seen[jan]:
            seen[jan] = profit

    return [j for j, _ in sorted(seen.items(), key=lambda x: x[1], reverse=True)]


if __name__ == "__main__":
    jans = get_restock_candidates(min_profit=0)
    print(f"=== 在庫切れ復活監視対象 ===")
    print(f"検出数: {len(jans)}件")
    for jan in jans[:20]:
        print(f"  {jan}")
    if not jans:
        print("対象なし（cache_results.json に在庫切れ利益商品が記録されるまで待機）")
