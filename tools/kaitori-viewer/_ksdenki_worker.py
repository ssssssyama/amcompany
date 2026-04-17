"""ケーズデンキオンライン検索ワーカー（サブプロセスとして実行される）

検索URL: https://www.ksdenki.com/shop/e/search/?keyword={JAN}
ブラウザ: Chromium

bot対策が厳しいため以下を実施:
  - Google検索経由の遷移をリファラーで模倣
  - 人間的なスクロール・マウス移動・ランダム待機
  - トップページ経由の自然な遷移

CDP接続モード: 実Chromeに接続してTLS/HTTP2フィンガープリント検知を回避する。
"""
import re
import sys

from _worker_common import (
    MAX_VERIFY, extract_selling_price,
    human_delay, human_like_goto, human_mouse_move, human_scroll,
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
        human_like_goto(page, url)

        title_el = page.query_selector("h1, .goods_name, .productName, .product-name")
        title = title_el.text_content().strip()[:200] if title_el else ""

        if title and is_used_or_excluded(title):
            return None
        if title and is_accessory(title):
            return None

        page_text = page.text_content("body") or ""

        # 在庫確認
        if any(kw in page_text for kw in ["販売終了", "品切れ", "在庫なし", "入荷未定"]):
            return None
        if "カートに入れる" in page_text or "在庫あり" in page_text:
            candidate["stock_status"] = "in_stock"
        elif "お取り寄せ" in page_text or "予約受付" in page_text:
            candidate["stock_status"] = "limited"

        # 価格取得（ポイント額除外）
        page_price = None
        for sel in [".goods_price .price", ".goods_price", ".itemPrice",
                    ".productPrice", "[class*='price']:not([class*='point'])"]:
            el = page.query_selector(sel)
            if el:
                extracted = extract_selling_price(el.text_content())
                if extracted:
                    page_price = extracted
                    break

        if not page_price:
            page_price = extract_selling_price(page_text)

        if not page_price:
            print(f"verify: price not found on page {url}", file=sys.stderr)
            return None

        if not verify_price_consistency(search_price, page_price):
            print(f"verify: price mismatch search={search_price} page={page_price}", file=sys.stderr)
            return None

        candidate["price"] = page_price

        # ケーズデンキはポイント制ではなく「あんしんパスポート」値引き
        # 一般的にはポイント0で扱う
        candidate["points"] = 0

        # JAN検証
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
    # トップページ経由（Cookieセッション確立 + 自然な遷移パターン）
    page = context.new_page()
    try:
        page.goto("https://www.ksdenki.com/", timeout=20000, wait_until="domcontentloaded")
        human_delay(2.0, 4.0)
        human_mouse_move(page)
        human_scroll(page, steps=1)
    except Exception:
        pass

    # 検索ページへ遷移
    search_url = f"https://www.ksdenki.com/shop/e/search/?keyword={jan_code}"
    human_like_goto(page, search_url)

    candidates = []

    # 検索結果から候補を収集
    item_selectors = [
        ".goods_list li",
        ".productItem",
        ".search-result-item",
        ".itemList li",
        "[class*='goods'][class*='item']",
        ".product-list li",
    ]
    items = []
    for sel in item_selectors:
        items = page.query_selector_all(sel)
        if items:
            break

    for item in items[:8]:
        text = item.text_content() or ""

        name = ""
        for name_sel in ["a[href*='/goods/']", "a[href*='/product/']",
                         "h3", "h2", ".goods_name", ".productName"]:
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
        for link_sel in ["a[href*='/goods/']", "a[href*='/product/']", "a[href]"]:
            el = item.query_selector(link_sel)
            if el:
                href = el.get_attribute("href") or ""
                if href.startswith("/"):
                    url = f"https://www.ksdenki.com{href}"
                elif href.startswith("http"):
                    url = href
                if url:
                    break

        if not url:
            continue

        stock_status = "unknown"
        if any(kw in text for kw in ["在庫あり", "カートに入れる"]):
            stock_status = "in_stock"
        elif "お取り寄せ" in text:
            stock_status = "limited"
        elif any(kw in text for kw in ["販売終了", "品切れ", "在庫なし"]):
            continue

        candidates.append({
            "name": name, "price": price, "shop": "ケーズデンキ",
            "url": url, "points": 0, "source": "ケーズデンキ",
            "stock_status": stock_status,
        })

    # フォールバック
    if not candidates:
        body_text = page.text_content("body") or ""
        price = extract_selling_price(body_text)
        if price:
            title_el = page.query_selector("h1, .goods_name")
            name = title_el.text_content().strip()[:120] if title_el else ""
            if name and not is_used_or_excluded(name) and page.url.startswith("http"):
                candidates.append({
                    "name": name, "price": price, "shop": "ケーズデンキ",
                    "url": page.url, "points": 0,
                    "source": "ケーズデンキ", "stock_status": "unknown",
                })

    candidates.sort(key=lambda x: x["price"])
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
    run_worker(search, extra_headers={
        "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.google.co.jp/",
    })
