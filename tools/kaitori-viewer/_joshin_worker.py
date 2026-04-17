"""ジョーシン検索ワーカー（サブプロセスとして実行される）

検索URL: https://joshinweb.jp/servlet/emall/search?keyword={JAN}
検索結果から候補を収集後、商品ページを訪問して除外条件を検証する。
"""
import random
import re
import sys
import time

from _worker_common import (
    MAX_VERIFY, extract_selling_price, is_accessory, is_used_or_excluded,
)


def _parse_points(text: str, price: int) -> int:
    pct_match = re.search(r"(\d{1,2})[%％]\s*(?:ポイント|還元)", text)
    if pct_match:
        return int(price * int(pct_match.group(1)) / 100)
    abs_match = re.search(r"([\d,]+)\s*ポイント", text)
    if abs_match:
        return int(abs_match.group(1).replace(",", ""))
    return int(price * 0.01)


def _verify_product_page(context, candidate, jan_code):
    url = candidate.get("url")
    if not url:
        return None

    page = context.new_page()
    try:
        page.goto(url, timeout=15000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        time.sleep(random.uniform(1.5, 3.0))

        title_el = page.query_selector("h1, .productName, .goods_name")
        title = title_el.text_content().strip()[:200] if title_el else ""

        if title and is_used_or_excluded(title):
            return None
        if title and is_accessory(title):
            return None

        detail_el = page.query_selector(".goodsDetail, .productDetail, .itemDetail")
        detail_text = detail_el.text_content() if detail_el else ""
        if any(kw in detail_text for kw in ["中古品", "アウトレット品", "展示品"]):
            return None

        page_text = page.text_content("body") or ""
        if "販売終了" in page_text or "品切れ" in page_text or "完売" in page_text:
            return None
        if "在庫あり" in page_text or "カートに入れる" in page_text:
            candidate["stock_status"] = "in_stock"
        elif "お取り寄せ" in page_text or "予約" in page_text:
            candidate["stock_status"] = "limited"

        for price_sel in [".priceArea .price", ".sellingPrice", ".priceArea"]:
            price_el = page.query_selector(price_sel)
            if price_el:
                m = re.search(r"[\d,]+", price_el.text_content())
                if m:
                    page_price = int(m.group().replace(",", ""))
                    if page_price >= 1000:
                        candidate["price"] = page_price
                        break

        candidate["points"] = _parse_points(page_text, candidate["price"])

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
            f"https://joshinweb.jp/servlet/emall/search?keyword={jan_code}",
            timeout=20000,
        )
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        time.sleep(random.uniform(2.0, 4.0))

        candidates = []

        item_selectors = [
            ".srsList li", ".productList li", ".search_list li",
            ".list_area li", "[class*='product'][class*='item']", ".goodsListArea li",
        ]
        items = []
        for sel in item_selectors:
            items = page.query_selector_all(sel)
            if items:
                break

        for item in items[:10]:
            text = item.text_content() or ""

            name = ""
            for name_sel in ["a[href*='/servlet/emall/']", "a[href*='joshinweb.jp']",
                             "h3", "h2", ".productName", ".goods_name"]:
                name_el = item.query_selector(name_sel)
                if name_el:
                    candidate_name = name_el.text_content().strip()[:120]
                    if len(candidate_name) > 5:
                        name = candidate_name
                        break

            if not name or is_used_or_excluded(name):
                continue

            price = None
            for price_sel in [".priceArea .price", ".sellingPrice",
                              ".priceArea", ".price", "[class*='price']"]:
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
            link_el = (item.query_selector("a[href*='/servlet/emall/']")
                       or item.query_selector("a[href*='joshinweb.jp']")
                       or item.query_selector("a[href]"))
            if link_el:
                href = link_el.get_attribute("href") or ""
                if href.startswith("/"):
                    url = f"https://joshinweb.jp{href}"
                elif href.startswith("http"):
                    url = href

            if not url:
                continue

            stock_status = "unknown"
            if "在庫あり" in text:
                stock_status = "in_stock"
            elif "お取り寄せ" in text or "予約" in text:
                stock_status = "limited"
            elif "販売終了" in text or "品切れ" in text or "完売" in text:
                continue

            points = _parse_points(text, price)

            candidates.append({
                "name": name, "price": price, "shop": "Joshin webショップ",
                "url": url, "points": points, "source": "ジョーシン",
                "stock_status": stock_status,
            })

        if not candidates:
            body_text = page.text_content("body") or ""
            price = extract_selling_price(body_text)
            if price:
                title_el = page.query_selector("h1, .productName")
                name = title_el.text_content().strip()[:120] if title_el else ""
                if name and not is_used_or_excluded(name) and page.url.startswith("http"):
                    candidates.append({
                        "name": name, "price": price, "shop": "Joshin webショップ",
                        "url": page.url, "points": int(price * 0.01),
                        "source": "ジョーシン", "stock_status": "unknown",
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
    run_worker(search)
