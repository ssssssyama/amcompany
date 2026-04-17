"""Amazon検索ワーカー（サブプロセスとして実行される）

検索結果から候補を収集後、商品ページを訪問して除外条件を検証する。
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
    MAX_VERIFY, is_accessory, is_used_or_excluded,
)

jan_code = sys.argv[1]


def _extract_coupon(page) -> int:
    """商品ページからクーポン額を抽出する（0なら未検出）"""
    selectors = [
        "#promoPriceBlockMessage_feature_div",
        "#couponBadgeRegularVpc",
        "[data-feature-name='acBadge']",
        ".couponBadge",
        "#vpcButton",
    ]
    for sel in selectors:
        el = page.query_selector(sel)
        if not el:
            continue
        text = el.text_content() or ""
        # 「￥500 OFF」「500円OFF」「500円引き」パターン
        m = re.search(r"[￥¥]?\s*(\d{1,3}(?:,\d{3})*)\s*円?\s*(?:OFF|off|引き|割引|クーポン)", text)
        if m:
            return int(m.group(1).replace(",", ""))
        # 「5%OFF」パターン → 価格が必要なので後で計算
        m_pct = re.search(r"(\d{1,2})\s*[%％]\s*(?:OFF|off|割引|クーポン)", text)
        if m_pct:
            price = page.query_selector(
                "#corePrice_feature_div .a-offscreen, "
                ".a-price:not([data-a-strike]) .a-offscreen"
            )
            if price:
                pm = re.search(r"[\d,]+", price.text_content())
                if pm:
                    base = int(pm.group().replace(",", ""))
                    return int(base * int(m_pct.group(1)) / 100)
    return 0


def _verify_product_page(context, candidate):
    """商品ページを訪問し、除外条件を検証する。検証失敗時は None を返す。"""
    url = candidate.get("url")
    if not url:
        return None

    page = context.new_page()
    try:
        page.goto(url, timeout=15000)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        time.sleep(random.uniform(1.0, 2.5))

        title_el = page.query_selector("#productTitle, #title, h1 span, h1")
        title = title_el.text_content().strip()[:200] if title_el else ""

        if title and is_used_or_excluded(title):
            return None
        if title and is_accessory(title):
            return None

        detail_el = page.query_selector("#centerCol, #ppd, #dp-container")
        detail_text = detail_el.text_content() if detail_el else ""
        if "Amazon Renewed" in detail_text or "整備済み品" in detail_text:
            return None
        if "この商品は中古品です" in detail_text:
            return None

        avail_el = page.query_selector("#availability, #outOfStock")
        avail_text = avail_el.text_content() if avail_el else ""
        if "在庫切れ" in avail_text or "入荷時期は未定" in avail_text:
            return None
        if "在庫あり" in avail_text or "お届け" in avail_text:
            candidate["stock_status"] = "in_stock"
        elif "残り" in avail_text:
            candidate["stock_status"] = "limited"

        price_el = page.query_selector(
            "#corePrice_feature_div .a-offscreen, "
            "#priceblock_ourprice, "
            "#priceblock_dealprice, "
            ".a-price:not([data-a-strike]) .a-offscreen"
        )
        if price_el:
            m = re.search(r"[\d,]+", price_el.text_content())
            if m:
                page_price = int(m.group().replace(",", ""))
                if page_price >= 1000:
                    candidate["price"] = page_price

        # クーポン額の抽出
        coupon = _extract_coupon(page)
        if coupon > 0:
            candidate["coupon"] = coupon

        if title:
            candidate["name"] = title[:120]

        return candidate
    except Exception as e:
        # ページ読み込み失敗時は検証できないため棄却
        print(f"verify error: {e}", file=sys.stderr)
        return None
    finally:
        page.close()


try:
    from playwright.sync_api import sync_playwright
    from stealth import create_stealth_context

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, timeout=15000)
        try:
            context = create_stealth_context(browser)
            page = context.new_page()
            page.goto(f"https://www.amazon.co.jp/s?k={jan_code}&condition=new", timeout=15000)
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            time.sleep(random.uniform(1.5, 3.5))

            items = page.query_selector_all('[data-component-type="s-search-result"]')

            candidates = []
            for item in items[:10]:
                asin = item.get_attribute("data-asin") or ""
                if not asin:
                    continue

                name_el = item.query_selector("h2")
                name = name_el.text_content().strip()[:120] if name_el else ""

                if is_used_or_excluded(name):
                    continue

                text = item.text_content()

                if "中古品" in text:
                    continue
                if "Amazon Renewed" in text or "整備済み品" in text:
                    continue

                price = None
                price_el = item.query_selector(".a-price:not([data-a-strike]) .a-offscreen")
                if price_el:
                    price_text = price_el.text_content().strip()
                    m = re.search(r"[\d,]+", price_text)
                    if m:
                        price = int(m.group().replace(",", ""))

                if not price:
                    before_used = text.split("中古品")[0] if "中古品" in text else text
                    yen_matches = re.findall(r"[￥¥](\d{1,3}(?:,\d{3})+)", before_used)
                    if yen_matches:
                        price_candidates = [int(m.replace(",", "")) for m in yen_matches if int(m.replace(",", "")) >= 1000]
                        if price_candidates:
                            price = min(price_candidates)

                if not price:
                    before_used = text.split("中古品")[0] if "中古品" in text else text
                    bare_matches = re.findall(r"(\d{1,3}(?:,\d{3})+)", before_used)
                    price_candidates = [int(m.replace(",", "")) for m in bare_matches if int(m.replace(",", "")) >= 1000]
                    if price_candidates:
                        price = min(price_candidates)

                if not price:
                    continue

                stock_status = "unknown"
                if "在庫あり" in text:
                    stock_status = "in_stock"
                elif "残り" in text:
                    stock_status = "limited"
                elif "お届け" in text or "明日" in text:
                    stock_status = "in_stock"

                # 検索結果からクーポンバッジを検出
                coupon = 0
                coupon_el = item.query_selector("[data-component-type='s-coupon-component'], .s-coupon-unclipped")
                if coupon_el:
                    coupon_text = coupon_el.text_content() or ""
                    cm = re.search(r"[￥¥]?\s*(\d{1,3}(?:,\d{3})*)\s*円?\s*(?:OFF|off|引き|割引|クーポン)", coupon_text)
                    if cm:
                        coupon = int(cm.group(1).replace(",", ""))

                entry = {
                    "name": name, "price": price, "shop": "Amazon.co.jp",
                    "url": f"https://www.amazon.co.jp/dp/{asin}",
                    "points": 0, "source": "Amazon",
                    "stock_status": stock_status,
                }
                if coupon > 0:
                    entry["coupon"] = coupon
                candidates.append(entry)

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
