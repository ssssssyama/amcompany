"""価格.com検索ワーカー（サブプロセスとして実行される）

価格.comで最安値を取得し、その店舗の実際の商品ページに遷移して
販売価格・除外条件・在庫を検証する2段階方式。

検索URL: https://search.kakaku.com/{JAN}/
ブラウザ: Chromium

価格.comの遷移URLパターン:
  検索結果: kakaku.com/ksearch/jump/?u={encoded_url}
  商品詳細: kakaku.com/forwarder/forward.aspx?...&Url={encoded_url}
"""
import io
import json
import random
import re
import sys
import time
from urllib.parse import urlparse

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from _worker_common import (
    MAX_VERIFY, decode_kakaku_redirect, extract_selling_price,
    human_delay, human_like_goto, human_mouse_move, human_scroll,
    is_accessory, is_used_or_excluded, verify_price_consistency,
)

jan_code = sys.argv[1]


def _verify_shop_page(context, candidate):
    """実店舗の商品ページを訪問して価格・除外条件・在庫を検証する。

    価格.comの最安値は参考値であり、実店舗で確認が必須。
    検証に失敗した場合は None を返す。
    """
    shop_url = candidate.get("shop_url", "")
    if not shop_url or not shop_url.startswith("http"):
        return None

    kakaku_price = candidate["price"]  # 価格.com上の参考価格

    page = context.new_page()
    try:
        human_like_goto(page, shop_url, timeout=20000)

        page_text = page.text_content("body") or ""

        # 商品名取得
        title_el = page.query_selector("h1, [class*='product'][class*='name'], [class*='goods'][class*='name']")
        title = title_el.text_content().strip()[:200] if title_el else ""

        # 除外条件チェック
        if title and is_used_or_excluded(title):
            print(f"shop verify: excluded (used/excluded) {title[:50]}", file=sys.stderr)
            return None
        if title and is_accessory(title):
            print(f"shop verify: excluded (accessory) {title[:50]}", file=sys.stderr)
            return None

        # 商品説明内の中古・アウトレット表記
        for kw in ["中古品", "アウトレット品", "展示品", "整備済み品"]:
            if kw in page_text:
                print(f"shop verify: excluded ({kw})", file=sys.stderr)
                return None

        # 在庫確認
        if any(kw in page_text for kw in ["販売終了", "品切れ", "在庫なし", "入荷未定", "売り切れ", "取扱終了"]):
            print(f"shop verify: out of stock", file=sys.stderr)
            return None

        if "カートに入れる" in page_text or "今すぐ買う" in page_text or "在庫あり" in page_text:
            candidate["stock_status"] = "in_stock"
        elif "お取り寄せ" in page_text or "予約" in page_text:
            candidate["stock_status"] = "limited"

        # 実際の販売価格を取得（ポイント額除外）
        shop_price = extract_selling_price(page_text)

        if not shop_price:
            # ￥がない場合、税込価格パターンを試行
            tax_match = re.search(r"([\d,]+)\s*円\s*[（(]税込", page_text)
            if tax_match:
                shop_price = int(tax_match.group(1).replace(",", ""))

        if not shop_price:
            print(f"shop verify: price not found on {shop_url[:60]}", file=sys.stderr)
            return None

        # 価格.com価格と実店舗価格の乖離チェック
        if not verify_price_consistency(kakaku_price, shop_price):
            print(f"shop verify: price mismatch kakaku={kakaku_price} shop={shop_price}", file=sys.stderr)
            return None

        # 実店舗の価格で上書き
        candidate["price"] = shop_price
        candidate["url"] = page.url  # リダイレクト後の実URL

        # ポイント取得
        pt_match = re.search(r"(\d{1,2})[%％]\s*(?:ポイント|還元)", page_text)
        if pt_match:
            candidate["points"] = int(shop_price * int(pt_match.group(1)) / 100)
        else:
            pt_abs = re.search(r"[￥¥]?([\d,]+)\s*(?:ポイント|円相当)", page_text)
            if pt_abs:
                candidate["points"] = int(pt_abs.group(1).replace(",", ""))

        if title:
            candidate["name"] = title[:120]

        return candidate
    except Exception as e:
        print(f"shop verify error: {e}", file=sys.stderr)
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

            # 価格.com検索
            search_url = f"https://search.kakaku.com/{jan_code}/"
            human_like_goto(page, search_url)

            candidates = []

            # --- 戦略1: 検索結果ページのショップ一覧から取得 ---
            body_text = page.text_content("body") or ""

            # 「ショップへ移動」リンクを全て取得
            links = page.query_selector_all("a[href*='kakaku.com/ksearch/jump'], a[href*='kakaku.com/forwarder/forward']")

            for link in links[:10]:
                kakaku_href = link.get_attribute("href") or ""
                if not kakaku_href:
                    continue

                shop_url = decode_kakaku_redirect(kakaku_href)
                if not shop_url.startswith("http"):
                    continue

                # リンクの前後テキストからショップ名・価格を取得
                parent = link.evaluate("el => el.closest('div, li, tr, section') || el.parentElement")
                parent_el = link.evaluate_handle("el => el.closest('div, li, tr, section') || el.parentElement")
                parent_text = parent_el.evaluate("el => el ? el.textContent : ''") if parent_el else ""

                if not parent_text:
                    parent_text = link.text_content() or ""

                price = extract_selling_price(parent_text)
                if not price:
                    # ￥なしの価格パターン
                    price_match = re.search(r"([\d,]+)\s*円", parent_text)
                    if price_match:
                        price = int(price_match.group(1).replace(",", ""))

                if not price or price < 1000:
                    continue

                # ショップ名（リンクテキストまたは周辺テキスト）
                shop_name = "価格.com経由"
                # URLからショップドメインを推定
                try:
                    shop_domain = urlparse(shop_url).hostname or ""
                    shop_domain = shop_domain.replace("www.", "").split(".")[0]
                    if shop_domain:
                        shop_name = shop_domain
                except Exception:
                    pass

                candidates.append({
                    "name": "",  # 後で店舗ページから取得
                    "price": price,
                    "shop": shop_name,
                    "url": shop_url,
                    "shop_url": shop_url,
                    "kakaku_url": kakaku_href,
                    "points": 0,
                    "source": "価格.com",
                    "stock_status": "unknown",
                })

            # --- 戦略2: ページ全体から最安値を取得（検索結果が構造化されてない場合） ---
            if not candidates:
                # 最安値をページテキストから取得
                price = extract_selling_price(body_text)
                if price:
                    # 最初のショップ遷移リンクを取得
                    first_link = page.query_selector("a[href*='ksearch/jump'], a[href*='forwarder/forward']")
                    if first_link:
                        href = first_link.get_attribute("href") or ""
                        shop_url = decode_kakaku_redirect(href)
                        if shop_url.startswith("http"):
                            candidates.append({
                                "name": "", "price": price, "shop": "価格.com経由",
                                "url": shop_url, "shop_url": shop_url,
                                "kakaku_url": href, "points": 0,
                                "source": "価格.com", "stock_status": "unknown",
                            })

            # 安い順にソート、重複店舗URLを除去
            seen_urls = set()
            unique = []
            for c in sorted(candidates, key=lambda x: x["price"]):
                if c["shop_url"] not in seen_urls:
                    seen_urls.add(c["shop_url"])
                    unique.append(c)
            candidates = unique

            page.close()

            # --- 実店舗ページで検証（上位5件まで、検証成功は最大3件） ---
            verified_results = []
            for c in candidates[:5]:
                if len(verified_results) >= MAX_VERIFY:
                    break
                print(f"verifying shop: {c['shop']} ¥{c['price']:,} {c['shop_url'][:60]}", file=sys.stderr)
                verified = _verify_shop_page(context, c)
                if verified:
                    verified.pop("shop_url", None)
                    verified.pop("kakaku_url", None)
                    verified_results.append(verified)

        finally:
            browser.close()

    # 複数結果をJSON配列で出力（後方互換: 0件ならnull）
    if verified_results:
        print(json.dumps(verified_results, ensure_ascii=False))
    else:
        print("null")

except Exception as e:
    print("null")
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
