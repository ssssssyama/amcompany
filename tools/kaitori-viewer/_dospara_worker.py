"""ドスパラ検索ワーカー（PC専門、商品名検索方式）

ドスパラは JAN 検索をサポートしないため、**商品名をキーワードに検索**する。
検索結果に対して rapidfuzz で類似度検証し、60%以上一致するものだけ採用。

引数:
  sys.argv[1]: JAN (ログ用)
  sys.argv[2]: 商品名（検索キーワードとして使用、必須）
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from _worker_common import (
    ACCESSORY_KEYWORDS, extract_selling_price, is_used_or_excluded,
)

_OUT_OF_STOCK_MARKERS = [
    "在庫なし", "品切れ", "売り切れ", "SOLD OUT",
    "販売終了", "取扱終了", "販売休止",
    "入荷待ち", "入荷未定", "ご注文できません",
]
_LIMITED_STOCK_MARKERS = [
    "在庫わずか", "残りわずか", "お取り寄せ", "予約",
]


def _detect_stock_status_from_card(text: str) -> str:
    """商品カードテキストから在庫状況を判定"""
    if any(kw in text for kw in _OUT_OF_STOCK_MARKERS):
        return "out_of_stock"
    if any(kw in text for kw in _LIMITED_STOCK_MARKERS):
        return "limited"
    return "in_stock"

jan_code = sys.argv[1]
product_name = sys.argv[2] if len(sys.argv) > 2 else ""

# 商品名がない場合はドスパラでは検索できない（JANでは404になる）
if not product_name:
    print("null")
    sys.exit(0)


def _similarity_ok(csv_name: str, ec_name: str, threshold: float = 60.0) -> bool:
    """rapidfuzz で商品名類似度を確認（未インストール時は簡易チェック）"""
    try:
        from rapidfuzz import fuzz
        ratio = fuzz.token_set_ratio(csv_name[:80], ec_name[:80])
        return ratio >= threshold
    except ImportError:
        # フォールバック: 英数字トークンの重複率
        csv_tokens = set(re.findall(r"[A-Za-z0-9]{2,}", csv_name.upper()))
        ec_tokens = set(re.findall(r"[A-Za-z0-9]{2,}", ec_name.upper()))
        if not csv_tokens:
            return False
        overlap = csv_tokens & ec_tokens
        return len(overlap) / len(csv_tokens) >= 0.5


def _extract_search_keyword(name: str) -> str:
    """商品名から有効な検索キーワードを生成（長すぎる場合は短縮）"""
    # カッコ類を除去して空白区切りに
    cleaned = re.sub(r"[()（）\[\]【】「」/／・]", " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # 最初の60文字まで（ドスパラは長すぎるクエリで0件になりやすい）
    return cleaned[:60]


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("null")
        return

    keyword = _extract_search_keyword(product_name)
    if not keyword:
        print("null")
        return

    from urllib.parse import quote
    url = f"https://www.dospara.co.jp/products/all-item?q={quote(keyword)}"

    try:
        from stealth import create_stealth_context, launch_stealth_browser, safe_goto
    except ImportError:
        print("null")
        return

    try:
        with sync_playwright() as p:
            browser = launch_stealth_browser(p, prefer="chromium")
            context = create_stealth_context(browser)
            page = context.new_page()
            ok = safe_goto(
                page, url,
                warmup_url="https://www.dospara.co.jp/",
                timeout=20000, max_retries=1,
                post_delay=(2.0, 4.0),
            )
            if not ok:
                print("null")
                browser.close()
                return

            # 商品カード
            cards = page.query_selector_all(".product.p-products-all-item-product")

            for card in cards[:15]:
                text = (card.text_content() or "").strip()
                if len(text) < 20:
                    continue

                # 中古・アクセサリ除外
                if is_used_or_excluded(text[:400]):
                    continue
                text_lower = text.lower()
                if any(kw.lower() in text_lower for kw in ACCESSORY_KEYWORDS[:15]):
                    continue

                # 価格取得（.p-products-all-item-product__price）
                price_el = card.query_selector(".p-products-all-item-product__price")
                price = None
                if price_el:
                    price = extract_selling_price(price_el.text_content() or "")
                if not price:
                    price = extract_selling_price(text)
                if not price or price < 1000:
                    continue

                # 商品名類似度チェック
                if not _similarity_ok(product_name, text[:200]):
                    continue

                # URL
                link_el = card.query_selector("a[href]")
                ec_url = ""
                if link_el:
                    href = link_el.get_attribute("href") or ""
                    if href.startswith("/"):
                        ec_url = "https://www.dospara.co.jp" + href
                    elif href.startswith("http"):
                        ec_url = href

                # 商品名（カード内の最初の意味のある行）
                name_lines = [l.strip() for l in text.split("\n") if l.strip()]
                name = next((l for l in name_lines if len(l) > 15 and not l.startswith(("中古", "状態"))), product_name)[:200]

                stock_status = _detect_stock_status_from_card(text[:600])
                # 在庫切れ商品はスキップ（買取店ルートでは仕入不可）
                if stock_status == "out_of_stock":
                    continue

                result = {
                    "name": name,
                    "price": price,
                    "shop": "ドスパラ",
                    "url": ec_url,
                    "points": int(price * 0.01),
                    "source": "ドスパラ",
                    "stock_status": stock_status,
                }
                browser.close()
                print(json.dumps(result, ensure_ascii=False))
                return

            browser.close()
            print("null")

    except Exception as e:
        print("null")
        print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
