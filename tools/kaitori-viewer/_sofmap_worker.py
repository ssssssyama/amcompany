"""ソフマップ検索ワーカー（サブプロセスとして実行される）

検索URL: https://www.sofmap.com/search_result.aspx?keyword={JAN}
ブラウザ: CDP接続（実Chrome）

ソフマップはPlaywright headlessでブロックされるため、CDP接続モードで実行する。
"""
import random
import re
import sys
import time

from _worker_common import (
    MAX_VERIFY, extract_selling_price,
    is_accessory, is_used_or_excluded, verify_price_consistency,
)


def _verify_product_page(context, candidate, jan_code):
    """商品ページを訪問し、除外条件を検証する。"""
    url = candidate.get("url")
    if not url:
        return None

    search_price = candidate["price"]

    page = context.new_page()
    try:
        page.goto(url, timeout=15000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        time.sleep(random.uniform(1.5, 3.0))

        title_el = page.query_selector("h1, .product_name, .productName")
        title = title_el.text_content().strip()[:200] if title_el else ""

        if title and is_used_or_excluded(title):
            return None
        if title and is_accessory(title):
            return None

        page_text = page.text_content("body") or ""
        if "販売終了" in page_text or "品切れ" in page_text or "在庫なし" in page_text:
            return None
        if "在庫あり" in page_text or "カートに入れる" in page_text:
            candidate["stock_status"] = "in_stock"
        elif "お取り寄せ" in page_text:
            candidate["stock_status"] = "limited"

        page_price = None
        for sel in [".product_price", ".salesPrice", "[class*='price']"]:
            el = page.query_selector(sel)
            if el:
                m = re.search(r"[\d,]+", el.text_content())
                if m:
                    val = int(m.group().replace(",", ""))
                    if val >= 1000:
                        page_price = val
                        break

        if not page_price:
            page_price = extract_selling_price(page_text)

        if not page_price:
            return None

        if not verify_price_consistency(search_price, page_price):
            return None

        candidate["price"] = page_price

        pt_match = re.search(r"(\d{1,2})[%％]\s*(?:ポイント|還元)", page_text)
        if pt_match:
            pt_rate = int(pt_match.group(1)) / 100
            candidate["points"] = int(page_price * pt_rate)

        jan_match = re.search(r"(?:JAN|JANコード|バーコード)[：:\s]*(\d{13})", page_text)
        if jan_match and jan_match.group(1) != jan_code:
            return None

        if title:
            candidate["name"] = title[:120]

        return candidate
    except Exception as e:
        print(f"verify error: {e}", file=sys.stderr)
        return None
    finally:
        page.close()


def search(context, jan_code):
    page = context.new_page()
    try:
        page.goto(
            f"https://www.sofmap.com/search_result.aspx?keyword={jan_code}",
            timeout=20000,
        )
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        time.sleep(random.uniform(2.0, 4.0))

        candidates = []

        item_selectors = [
            ".product_list li",
            ".productItem",
            ".search-result-item",
            "[class*='product'][class*='item']",
        ]
        items = []
        for sel in item_selectors:
            items = page.query_selector_all(sel)
            if items:
                break

        for item in items[:10]:
            text = item.text_content() or ""

            name = ""
            for name_sel in ["a[href*='product']", "h3", "h2", ".product_name", ".productName"]:
                name_el = item.query_selector(name_sel)
                if name_el:
                    candidate_name = name_el.text_content().strip()[:120]
                    if len(candidate_name) > 3:
                        name = candidate_name
                        break

            if not name or is_used_or_excluded(name):
                continue

            price = None
            for price_sel in [".product_price", ".salesPrice", "[class*='price']"]:
                price_el = item.query_selector(price_sel)
                if price_el:
                    m = re.search(r"[\d,]+", price_el.text_content())
                    if m:
                        candidate_price = int(m.group().replace(",", ""))
                        if candidate_price >= 1000:
                            price = candidate_price
                            break

            if not price:
                price = extract_selling_price(text)
            if not price:
                continue

            url = ""
            link_el = item.query_selector("a[href*='product']") or item.query_selector("a[href]")
            if link_el:
                href = link_el.get_attribute("href") or ""
                if href.startswith("/"):
                    url = f"https://www.sofmap.com{href}"
                elif href.startswith("http"):
                    url = href

            if not url:
                continue

            stock_status = "unknown"
            if "在庫あり" in text:
                stock_status = "in_stock"
            elif "お取り寄せ" in text:
                stock_status = "limited"
            elif "販売終了" in text or "品切れ" in text:
                continue

            pt_match = re.search(r"(\d{1,2})[%％]\s*(?:ポイント|還元)", text)
            pt_rate = int(pt_match.group(1)) / 100 if pt_match else 0.10
            points = int(price * pt_rate)

            candidates.append({
                "name": name, "price": price, "shop": "ソフマップ",
                "url": url, "points": points, "source": "ソフマップ",
                "stock_status": stock_status,
            })

        # フォールバック
        if not candidates:
            body_text = page.text_content("body") or ""
            price = extract_selling_price(body_text)
            if price:
                title_el = page.query_selector("h1, .product_name")
                name = title_el.text_content().strip()[:120] if title_el else ""
                if name and not is_used_or_excluded(name) and page.url.startswith("http"):
                    candidates.append({
                        "name": name, "price": price, "shop": "ソフマップ",
                        "url": page.url, "points": int(price * 0.10),
                        "source": "ソフマップ", "stock_status": "unknown",
                    })

        candidates.sort(key=lambda x: x["price"])
    finally:
        page.close()

    best = None
    for c in candidates[:MAX_VERIFY]:
        verified = _verify_product_page(context, c, jan_code)
        if verified:
            best = verified
            break
    return best


if __name__ == "__main__" or not hasattr(sys, "ps1"):
    from _cdp_worker_common import run_worker
    run_worker(search, retailer_domain="www.sofmap.com")
