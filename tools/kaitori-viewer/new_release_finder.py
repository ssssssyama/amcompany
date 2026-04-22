"""新商品・予約商品検知（戦略I）

楽天/Yahoo のAPIでカメラ・ゲーム・グラボ関連の新商品（発売日が直近N日以内、
または未来日付=予約中）を検索し、CSVと交差したJANを返す。

使い方:
    from new_release_finder import find_new_releases
    jans = find_new_releases(csv_jans, days_within=30)

    # 単体テスト
    python new_release_finder.py
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Iterable

import requests
from dotenv import load_dotenv

from sale_finder import (
    _RAKUTEN_SALE_KEYWORDS, _extract_jan_from_text,
    RAKUTEN_HEADERS, _RAKUTEN_VALID, _rakuten_rate_limit,
    RAKUTEN_SEARCH_URL, _build_rakuten_params, _build_rakuten_headers,
)

logger = logging.getLogger(__name__)

load_dotenv()
RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID", "")
YAHOO_APP_ID = os.getenv("YAHOO_APP_ID", "")


def _parse_date(s: str) -> datetime | None:
    """YYYY-MM-DD や YYYYMMDD などのフォーマットを寛容にパース"""
    if not s:
        return None
    s = s.replace("/", "-").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y%m%d", "%Y"):
        try:
            return datetime.strptime(s[:len(fmt.replace("%Y", "YYYY").replace("%m", "mm").replace("%d", "dd"))], fmt)
        except ValueError:
            continue
    return None


def fetch_rakuten_new_release_jans(days_within: int = 30, max_per_keyword: int = 30) -> list[str]:
    """楽天で発売日順にソートし、直近 days_within 日以内または未来日付のJANを返す"""
    if not _RAKUTEN_VALID:
        return []  # sale_finder.py で起動時警告済み

    cutoff = datetime.now() - timedelta(days=days_within)
    jans: list[str] = []
    seen: set[str] = set()
    headers = _build_rakuten_headers()

    for keyword in _RAKUTEN_SALE_KEYWORDS:
        params = _build_rakuten_params({
            "keyword": keyword,
            "hits": min(max_per_keyword, 30),
            "sort": "-updateTimestamp",
            "availability": 1,
        })
        try:
            _rakuten_rate_limit()
            resp = requests.get(RAKUTEN_SEARCH_URL, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            for item_wrapper in data.get("Items", []):
                item = item_wrapper.get("Item", item_wrapper) if isinstance(item_wrapper, dict) else {}
                release_str = item.get("releaseDate", "")
                release_dt = _parse_date(release_str)
                # 発売日なしはスキップ（古い商品と区別できない）
                if not release_dt:
                    continue
                # カットオフ前のアイテムはスキップ（sortが発売日順ではないため break できない）
                if release_dt < cutoff:
                    continue

                name = item.get("itemName", "")
                for source in [name, item.get("itemCode", ""), item.get("itemUrl", "")]:
                    jan = _extract_jan_from_text(source)
                    if jan and jan not in seen:
                        jans.append(jan)
                        seen.add(jan)
                        break
        except (requests.RequestException, ValueError) as e:
            logger.warning("楽天新商品検索失敗 (%s): %s", keyword, e)

    logger.info("楽天新商品検索: %d件のJAN抽出 (直近%d日)", len(jans), days_within)
    return jans


def fetch_yahoo_new_release_jans(days_within: int = 30, max_per_keyword: int = 30) -> list[str]:
    """Yahooで新着順に検索し直近のJANを返す"""
    if not YAHOO_APP_ID:
        logger.warning("YAHOO_APP_ID が未設定")
        return []

    url = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
    jans: list[str] = []
    seen: set[str] = set()

    for keyword in _RAKUTEN_SALE_KEYWORDS:
        params = {
            "appid": YAHOO_APP_ID,
            "query": keyword,
            "results": min(max_per_keyword, 50),
            "sort": "-release_date",
            "in_stock": "true",
            "condition": "new",
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            for hit in data.get("hits", []):
                jan = hit.get("janCode") or _extract_jan_from_text(hit.get("name", ""))
                if jan and jan not in seen:
                    jans.append(jan)
                    seen.add(jan)
        except (requests.RequestException, ValueError) as e:
            logger.warning("Yahoo新商品検索失敗 (%s): %s", keyword, e)

    logger.info("Yahoo新商品検索: %d件のJAN抽出", len(jans))
    return jans


def find_new_releases(csv_jans: Iterable[str], days_within: int = 30) -> list[str]:
    """新商品・予約商品 ∩ 買取CSV のJANを返す"""
    csv_set = set(str(j) for j in csv_jans)
    if not csv_set:
        return []

    all_jans: list[str] = []
    all_jans.extend(fetch_rakuten_new_release_jans(days_within=days_within))
    all_jans.extend(fetch_yahoo_new_release_jans(days_within=days_within))

    seen: set[str] = set()
    intersection: list[str] = []
    for jan in all_jans:
        if jan in csv_set and jan not in seen:
            intersection.append(jan)
            seen.add(jan)

    logger.info("新商品 ∩ CSV: %d件", len(intersection))
    return intersection


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from pathlib import Path
    from csv_loader import load_csv

    CSV_DIR = Path(__file__).resolve().parent.parent.parent
    csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
    if not csv_files:
        print("CSVなし")
        exit(1)

    df = load_csv(str(csv_files[0]))
    csv_jans = set(df["JAN"].tolist())
    print(f"CSV JAN数: {len(csv_jans)}")

    intersection = find_new_releases(csv_jans, days_within=30)
    print(f"\n=== 新商品 ∩ CSV ===")
    print(f"該当: {len(intersection)}件")
    for jan in intersection[:20]:
        row = df[df["JAN"] == jan].iloc[0] if len(df[df["JAN"] == jan]) else None
        if row is not None:
            print(f"  {jan}: 買取{row['最高買取価格']:,}円 {row['商品名'][:40]}")
