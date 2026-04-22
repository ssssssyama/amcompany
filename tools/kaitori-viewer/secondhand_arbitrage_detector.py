"""中古市場アービトラージ検知（戦略R判定）

secondhand_history.json から、買取価格 < 駿河屋中古価格 - min_gap のJANを抽出。
中古を駿河屋に売る方が利益が出る商品を発見する。

使い方:
    from secondhand_arbitrage_detector import detect_secondhand_arbitrage
    cands = detect_secondhand_arbitrage(min_gap=500)

    # 単体テスト
    python secondhand_arbitrage_detector.py
"""

import json
from pathlib import Path

_HISTORY_FILE = Path.home() / ".kaitori-viewer" / "secondhand_history.json"


def _load_history() -> dict:
    if not _HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def detect_secondhand_arbitrage(min_gap: int = 500) -> list[tuple[str, int]]:
    """駿河屋中古最新価格 - min_gap > 買取最高値 のJANを返す。

    Args:
        min_gap: 価格差の最低額

    Returns:
        [(jan, used_price), ...] 中古価格降順
    """
    from csv_loader import load_csv
    CSV_DIR = Path(__file__).resolve().parent.parent.parent
    csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
    if not csv_files:
        return []

    df = load_csv(str(csv_files[0]))
    kaitori_map = {row["JAN"]: int(row["最高買取価格"]) for _, row in df.iterrows()}

    history = _load_history()
    if not history:
        return []

    results: list[tuple[str, int]] = []
    for jan, entries in history.items():
        if not isinstance(entries, list) or not entries:
            continue
        latest = entries[-1]
        if not isinstance(latest, dict):
            continue
        used_price = latest.get("used_price")
        if not isinstance(used_price, int) or used_price <= 0:
            continue
        kaitori = kaitori_map.get(jan, 0)
        if kaitori <= 0:
            continue
        if used_price - min_gap > kaitori:
            results.append((jan, used_price))

    return sorted(results, key=lambda x: x[1], reverse=True)


if __name__ == "__main__":
    cands = detect_secondhand_arbitrage(min_gap=500)
    print(f"=== 中古市場アービトラージ検知（駿河屋）===")
    print(f"検出数: {len(cands)}件")
    for jan, used in cands[:20]:
        print(f"  {jan}: 駿河屋中古{used:,}円")
    if not cands:
        print("候補なし（suruga_ya_scraper.py で履歴を蓄積してください）")
