"""ヤフオク利益確定検知（戦略J判定）

auction_history.json から、ヤフオク落札中央値 - min_gap > 買取最高値 のJANを抽出。
EC を経由せず買取→ヤフオク直販で利益確保できる候補。

使い方:
    from auction_relay_detector import detect_auction_arbitrage
    cands = detect_auction_arbitrage(min_gap=1000)

    # 単体テスト
    python auction_relay_detector.py
"""

import json
from pathlib import Path


_HISTORY_FILE = Path.home() / ".kaitori-viewer" / "auction_history.json"


def _load_history() -> dict:
    if not _HISTORY_FILE.exists():
        return {}
    try:
        return json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def detect_auction_arbitrage(min_gap: int = 1000) -> list[tuple[str, int, int]]:
    """ヤフオク中央値 - min_gap > 買取最高値 のJANを返す。

    Args:
        min_gap: 価格差の最低額（手数料考慮で1000円以上推奨）

    Returns:
        [(jan, median_price, kaitori), ...] 中央値降順
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

    results: list[tuple[str, int, int]] = []
    for jan, entries in history.items():
        if not isinstance(entries, list) or not entries:
            continue
        latest = entries[-1]
        if not isinstance(latest, dict):
            continue
        median = latest.get("median")
        if not isinstance(median, int) or median <= 0:
            continue
        kaitori = kaitori_map.get(jan, 0)
        if kaitori <= 0:
            continue
        if median - min_gap > kaitori:
            results.append((jan, median, kaitori))

    return sorted(results, key=lambda x: x[1] - x[2], reverse=True)


if __name__ == "__main__":
    cands = detect_auction_arbitrage(min_gap=1000)
    print(f"=== ヤフオク利益確定検知 ===")
    print(f"検出数: {len(cands)}件")
    for jan, median, kaitori in cands[:20]:
        print(f"  {jan}: ヤフオク{median:,}円 - 買取{kaitori:,}円 = +{median-kaitori:,}円")
    if not cands:
        print("候補なし（yauc_scraper.py で履歴を蓄積してください）")
