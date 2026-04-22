"""カメラのキタムラ検索ワーカー（カメラ専門、サブプロセスとして実行）

カメラ・ビデオカメラ・関連用品に強い。新品中心。
"""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from _worker_common import ACCESSORY_KEYWORDS, extract_selling_price, is_used_or_excluded

jan_code = sys.argv[1]


def _find_first_card(page, jan: str):
    cards = page.query_selector_all(
        ".item, .product, li[class*='item'], "
        "article, div[class*='product'], .productList li"
    )

    for card in cards[:15]:
        text = (card.text_content() or "").strip()
        if len(text) < 20:
            continue
        if is_used_or_excluded(text[:300]):
            continue
        text_lower = text.lower()
        if any(kw.lower() in text_lower for kw in ACCESSORY_KEYWORDS[:15]):
            continue

        price = extract_selling_price(text)
        if not price or price < 1000:
            continue

        link = card.query_selector("a[href]")
        url = ""
        if link:
            href = link.get_attribute("href") or ""
            if href.startswith("/"):
                url = "https://shop.kitamura.jp" + href
            elif href.startswith("http"):
                url = href

        name_el = card.query_selector("h2, h3, .item-name, .product-name, [class*='name']")
        name = (name_el.text_content().strip() if name_el else text[:100])[:200]

        return {"name": name, "price": price, "url": url}

    return None


def main():
    try:
        from playwright.sync_api import sync_playwright
        from stealth import create_stealth_context, launch_stealth_browser, safe_goto
    except ImportError:
        print(json.dumps({"error": "playwright not installed"}))
        return

    url = f"https://shop.kitamura.jp/ja/search/?keywords={jan_code}"

    try:
        with sync_playwright() as p:
            browser = launch_stealth_browser(p, prefer="chromium")
            context = create_stealth_context(browser)
            page = context.new_page()
            ok = safe_goto(
                page, url,
                warmup_url="https://shop.kitamura.jp/",
                timeout=20000, max_retries=1,
                post_delay=(1.5, 3.0),
            )
            if not ok:
                print("null")
                browser.close()
                return

            data = _find_first_card(page, jan_code)
            browser.close()

            if not data:
                print("null")
                return

            print(json.dumps({
                "name": data["name"],
                "price": data["price"],
                "shop": "カメラのキタムラ",
                "url": data["url"],
                "points": int(data["price"] * 0.01),
                "source": "キタムラ",
                "stock_status": "in_stock",
            }, ensure_ascii=False))
    except Exception as e:
        print("null")
        print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
