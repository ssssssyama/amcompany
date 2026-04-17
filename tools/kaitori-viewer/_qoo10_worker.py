"""Qoo10検索ワーカー（サブプロセスとして実行される）

検索URL: https://www.qoo10.jp/s/{JAN}?keyword={JAN}
ブラウザ: Chromium
"""
import io
import json
import random
import re
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from _worker_common import (
    MAX_VERIFY, extract_selling_price,
    human_delay, human_like_goto,
    is_accessory, is_used_or_excluded, verify_price_consistency,
)

jan_code = sys.argv[1]


def _verify_product_page(context, candidate):
    """商品ページを訪問し、除外条件を検証する。"""
    url = candidate.get("url")
    if not url:
        return None

    search_price = candidate["price"]

    page = context.new_page()
    try:
        human_like_goto(page, url)

        title_el = page.query_selector("h1, .tt_txt, .goods-title, .pd_tit")
        title = title_el.text_content().strip()[:200] if title_el else ""

        if title and is_used_or_excluded(title):
            return None
        if title and is_accessory(title):
            return None

        page_text = page.text_content("body") or ""

        # 在庫確認
        if any(kw in page_text for kw in ["品切れ", "売り切れ", "販売終了", "SOLD OUT"]):
            return None
        if "カートに入れる" in page_text or "今すぐ購入" in page_text:
            candidate["stock_status"] = "in_stock"

        # 価格取得
        page_price = None
        for sel in [".prc_t", ".price_real", ".goods-price", ".pd_price",
                    "[class*='price'] strong", "[class*='Price']"]:
            el = page.query_selector(sel)
            if el:
                extracted = extract_selling_price(el.text_content())
                if extracted:
                    page_price = extracted
                    break

        if not page_price:
            page_price = extract_selling_price(page_text)

        if not page_price:
            return None

        if not verify_price_consistency(search_price, page_price):
            return None

        candidate["price"] = page_price
        candidate["points"] = 0  # Qoo10はポイント還元が複雑なため0

        if title:
            candidate["name"] = title[:120]

        return candidate
    except Exception as e:
        print(f"verify error: {e}", file=sys.stderr)
        return None
    finally:
        page.close()


try:
    from playwright.sync_api import sync_playwright
    from stealth import create_stealth_context

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, timeout=20000)
        try:
            context = create_stealth_context(browser)
            page = context.new_page()

            search_url = f"https://www.qoo10.jp/s/{jan_code}?keyword={jan_code}"
            human_like_goto(page, search_url)

            candidates = []

            # 検索結果から候補を収集
            item_selectors = [
                ".gd_wrp",
                ".item_box",
                "[class*='goods_list'] li",
                ".search_item",
                ".product-item",
            ]
            items = []
            for sel in item_selectors:
                items = page.query_selector_all(sel)
                if items:
                    break

            for item in items[:8]:
                text = item.text_content() or ""

                name = ""
                for name_sel in ["a.gd_name", ".gd_name", "a.tt_txt",
                                 "h3", ".item_title", ".goods-name"]:
                    el = item.query_selector(name_sel)
                    if el:
                        candidate_name = el.text_content().strip()[:120]
                        if len(candidate_name) > 3:
                            name = candidate_name
                            break

                if not name or is_used_or_excluded(name):
                    continue

                price = extract_selling_price(text)
                if not price:
                    continue

                url = ""
                for link_sel in ["a[href*='/g/']", "a[href*='/item/']", "a[href]"]:
                    el = item.query_selector(link_sel)
                    if el:
                        href = el.get_attribute("href") or ""
                        if href.startswith("/"):
                            url = f"https://www.qoo10.jp{href}"
                        elif href.startswith("http"):
                            url = href
                        if url:
                            break

                if not url:
                    continue

                stock_status = "unknown"
                if "SOLD OUT" in text or "品切れ" in text:
                    continue
                if "カート" in text or "購入" in text:
                    stock_status = "in_stock"

                candidates.append({
                    "name": name, "price": price, "shop": "Qoo10",
                    "url": url, "points": 0, "source": "Qoo10",
                    "stock_status": stock_status,
                })

            # フォールバック
            if not candidates:
                body_text = page.text_content("body") or ""
                price = extract_selling_price(body_text)
                if price:
                    title_el = page.query_selector("h1, .tt_txt, .goods-title")
                    name = title_el.text_content().strip()[:120] if title_el else ""
                    if name and not is_used_or_excluded(name) and page.url.startswith("http"):
                        candidates.append({
                            "name": name, "price": price, "shop": "Qoo10",
                            "url": page.url, "points": 0,
                            "source": "Qoo10", "stock_status": "unknown",
                        })

            candidates.sort(key=lambda x: x["price"])
            page.close()

            best = None
            for c in candidates[:MAX_VERIFY]:
                verified = _verify_product_page(context, c)
                if verified:
                    best = verified
                    break
        finally:
            browser.close()

    print(json.dumps(best, ensure_ascii=False) if best else "null")

except Exception as e:
    print("null")
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
