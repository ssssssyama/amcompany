"""在庫再確認モジュール

EC検索で見つかった商品のページを実際に訪問し、在庫状況を再確認する。
- 楽天・Yahoo: requests で商品ページを取得しHTMLから在庫テキストを抽出
- Amazon: retailer_scraper の Playwright を利用
"""

import logging
import re

import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html",
}

# 在庫なしを示すキーワード
_OUT_OF_STOCK_KEYWORDS = [
    "在庫切れ",
    "売り切れ",
    "入荷待ち",
    "品切れ",
    "在庫なし",
    "sold out",
    "out of stock",
    "現在ご購入いただけません",
    "お取り扱いできません",
]

# 在庫限定を示すキーワード
_LIMITED_STOCK_KEYWORDS = [
    "残りわずか",
    "残り1点",
    "残り2点",
    "残り3点",
    "お取り寄せ",
]


def _check_stock_from_html(html: str) -> str:
    """HTMLテキストから在庫状況を判定する"""
    html_lower = html.lower()

    for keyword in _OUT_OF_STOCK_KEYWORDS:
        if keyword.lower() in html_lower:
            return "out_of_stock"

    for keyword in _LIMITED_STOCK_KEYWORDS:
        if keyword.lower() in html_lower:
            return "limited"

    # カートに入れるボタンがあれば在庫ありと判定
    if re.search(r"(カートに入れる|カートに追加|購入手続き|今すぐ買う|add.to.cart)", html_lower):
        return "in_stock"

    return "unknown"


def check_stock_single(url: str, source: str) -> str:
    """1つの商品URLの在庫を確認する

    Returns:
        "in_stock" | "limited" | "out_of_stock" | "unknown" | "error"
    """
    if not url:
        return "unknown"

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10, allow_redirects=True)
        resp.raise_for_status()
        return _check_stock_from_html(resp.text)
    except requests.RequestException as e:
        logger.warning("在庫確認エラー (%s): %s", url[:60], e)
        return "error"


def check_stock_batch(results: list[dict]) -> list[dict]:
    """検索結果リストの在庫を一括確認し、stock_status を更新して返す

    Args:
        results: EC検索結果の辞書リスト（"EC URL" と "ECソース" を含む）

    Returns:
        stock_status が更新された結果リスト
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _check_one(item):
        new_item = dict(item)
        url = item.get("EC URL", "")
        source = item.get("ECソース", "")

        if source == "Amazon":
            new_item.setdefault("在庫状況", _format_stock(item.get("stock_status", "unknown")))
        else:
            status = check_stock_single(url, source)
            new_item["stock_status"] = status
            new_item["在庫状況"] = _format_stock(status)

        return new_item

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(_check_one, item): i for i, item in enumerate(results)}
        updated = [None] * len(results)
        for future in as_completed(futures):
            idx = futures[future]
            try:
                updated[idx] = future.result()
            except Exception:
                updated[idx] = dict(results[idx])

    return updated


STOCK_LABELS = {
    "in_stock": "✅ 在庫あり",
    "limited": "⚠️ 残りわずか",
    "out_of_stock": "❌ 在庫なし",
    "unknown": "❓ 未確認",
    "error": "⚠️ 確認失敗",
}


def _format_stock(status: str) -> str:
    """stock_status を表示用ラベルに変換"""
    return STOCK_LABELS.get(status, "❓ 未確認")
