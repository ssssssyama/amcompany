"""商品名類似度マッチング（戦略Q）

CSVのJAN欠落行（商品名はあるがJANが空）を、商品名で楽天/Yahoo APIに
キーワード検索し、検索結果の商品名と rapidfuzz で類似度80%以上の
最高一致から JAN を抽出する。Gemini不使用、API費用ゼロ。

使い方:
    from name_matcher import match_product_name, recover_missing_jans
    jan, score = match_product_name("Sony WH-1000XM5")
    recovered = recover_missing_jans(df_no_jan)

    # 単体テスト
    python name_matcher.py
"""

import logging
import os
from typing import Iterable

import requests
from dotenv import load_dotenv

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None  # 未インストール時は recover_missing_jans が空辞書を返す

logger = logging.getLogger(__name__)

load_dotenv()
RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID", "")
YAHOO_APP_ID = os.getenv("YAHOO_APP_ID", "")

_MIN_SCORE = 80.0  # 類似度の最低閾値（%）

_RAKUTEN_HEADERS = {
    "Referer": "https://github.com/",
    "Origin": "https://github.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _extract_jan_from_text(text: str) -> str | None:
    import re
    if not text:
        return None
    m = re.search(r"(?<!\d)(\d{13})(?!\d)", text)
    if m:
        return m.group(1)
    m = re.search(r"(?<!\d)(\d{8})(?!\d)", text)
    if m:
        return m.group(1)
    return None


def _search_rakuten_by_name(name: str, max_results: int = 10) -> list[dict]:
    """楽天APIで商品名検索し、{name, jan} のリストを返す"""
    from sale_finder import (
        _RAKUTEN_VALID, _rakuten_rate_limit,
        RAKUTEN_SEARCH_URL, _build_rakuten_params, _build_rakuten_headers,
    )
    if not _RAKUTEN_VALID or not name:
        return []
    try:
        _rakuten_rate_limit()
        resp = requests.get(
            RAKUTEN_SEARCH_URL,
            params=_build_rakuten_params({
                "keyword": name[:60],
                "hits": min(max_results, 30),
                "availability": 1,
            }),
            headers=_build_rakuten_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        items = []
        for w in data.get("Items", []):
            it = w.get("Item", w) if isinstance(w, dict) else {}
            iname = it.get("itemName", "")
            jan = (
                _extract_jan_from_text(iname)
                or _extract_jan_from_text(it.get("itemCode", ""))
                or _extract_jan_from_text(it.get("itemUrl", ""))
            )
            if jan:
                items.append({"name": iname, "jan": jan})
        return items
    except (requests.RequestException, ValueError) as e:
        logger.debug("楽天検索失敗 (%s): %s", name[:30], e)
        return []


def _search_yahoo_by_name(name: str, max_results: int = 10) -> list[dict]:
    """Yahoo APIで商品名検索し、{name, jan} のリストを返す"""
    if not YAHOO_APP_ID or not name:
        return []
    try:
        resp = requests.get(
            "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch",
            params={
                "appid": YAHOO_APP_ID,
                "query": name[:60],
                "results": min(max_results, 50),
                "in_stock": "true",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        items = []
        for h in data.get("hits", []):
            iname = h.get("name", "")
            jan = h.get("janCode") or _extract_jan_from_text(iname)
            if jan:
                items.append({"name": iname, "jan": jan})
        return items
    except (requests.RequestException, ValueError) as e:
        logger.debug("Yahoo検索失敗 (%s): %s", name[:30], e)
        return []


def match_product_name(
    query_name: str,
    min_score: float = _MIN_SCORE,
) -> tuple[str, float] | None:
    """商品名でEC検索し、類似度 min_score 以上の最高一致から JAN を返す。

    Returns:
        (jan, similarity_score) or None
    """
    if not fuzz or not query_name:
        return None

    candidates: list[dict] = []
    candidates.extend(_search_rakuten_by_name(query_name))
    candidates.extend(_search_yahoo_by_name(query_name))
    if not candidates:
        return None

    best: tuple[str, float] | None = None
    for c in candidates:
        score = fuzz.token_set_ratio(query_name, c["name"])
        if score >= min_score and (best is None or score > best[1]):
            best = (c["jan"], float(score))

    return best


def recover_missing_jans(
    df_no_jan,
    name_col: str = "商品名",
    max_records: int = 100,
) -> dict[int, tuple[str, float]]:
    """JAN欠落行のインデックス → (推定JAN, 類似度) のマップを返す。

    Args:
        df_no_jan: JANなし行のDataFrame
        name_col: 商品名の列名
        max_records: 処理上限（API節約）

    Returns:
        {index: (jan, score)}
    """
    if not fuzz:
        logger.warning("rapidfuzz未インストール、戦略Qスキップ")
        return {}

    recovered: dict[int, tuple[str, float]] = {}
    for idx, row in df_no_jan.head(max_records).iterrows():
        name = str(row.get(name_col, "")).strip()
        if not name:
            continue
        result = match_product_name(name)
        if result:
            recovered[idx] = result
            logger.info("救済: %s → JAN %s (類似度%.1f)", name[:30], result[0], result[1])
    return recovered


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # テスト商品名
    samples = [
        "Sony WH-1000XM5 ヘッドホン",
        "Nintendo Switch 有機ELモデル",
        "Apple iPad Air 第5世代",
    ]
    for name in samples:
        result = match_product_name(name)
        if result:
            print(f"OK: {name} → JAN {result[0]} (類似度{result[1]:.1f})")
        else:
            print(f"NG: {name} → マッチなし")
