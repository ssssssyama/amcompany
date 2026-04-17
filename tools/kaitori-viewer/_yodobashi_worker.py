"""ヨドバシ検索ワーカー（サブプロセスとして実行される）

検索結果から候補を収集後、商品ページを訪問して除外条件を検証する。

価格抽出の注意点:
  ヨドバシの検索結果・商品ページでは販売価格とポイント還元額の両方に
  ￥マークが付く（例: ￥49,800 … ￥4,980ポイント）。
  min() で最安値を取るとポイント額を誤って販売価格と認識するため、
  価格要素のセレクタを限定し、ポイント表示との混同を防ぐ。
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
    ACCESSORY_KEYWORDS, MAX_VERIFY, encode_query,
    extract_selling_price, is_used_or_excluded, verify_price_consistency,
)

product_name = sys.argv[1]

search_keyword = re.sub(r"[()（）\[\]【】「」/／]", " ", product_name)
search_keyword = re.sub(r"\s+", " ", search_keyword).strip()[:50]


def _is_accessory_name(csv_name, ec_name):
    """EC商品名がアクセサリっぽいか判定（CSV側がアクセサリならスキップ）"""
    csv_l = csv_name.lower()
    ec_l = ec_name.lower()
    if any(kw in csv_l for kw in ACCESSORY_KEYWORDS):
        return False
    return any(kw in ec_l for kw in ACCESSORY_KEYWORDS)


def _is_model_mismatch(csv_name: str, ec_name: str) -> bool:
    """型番の不一致を検出する。

    「EOS R1」で検索して「EOS R10」がヒットするケースを防ぐ。
    CSV商品名から型番的な英数字トークンを抽出し、EC商品名に含まれるか確認する。
    """
    if not csv_name or not ec_name:
        return False

    # 型番トークンを抽出（英字+数字の組み合わせ、例: R1, X100VI, GR4, RTX4090）
    csv_tokens = set(re.findall(r"[A-Za-z]+\d+[A-Za-z]*\d*", csv_name))
    if not csv_tokens:
        return False

    ec_upper = ec_name.upper()
    for token in csv_tokens:
        token_upper = token.upper()
        # EC名にトークンが含まれるが、その直後に追加の数字/英字がある場合は不一致
        # 例: "R1" はあるが実際は "R10" → 不一致
        pos = ec_upper.find(token_upper)
        if pos == -1:
            # トークン自体がEC名にない → 不一致
            return True
        # トークンの直後の文字をチェック
        end_pos = pos + len(token_upper)
        if end_pos < len(ec_upper):
            next_char = ec_upper[end_pos]
            # 直後が数字 → 別型番（R1 vs R10）
            if next_char.isdigit():
                return True

    return False


def _verify_product_page(context, candidate):
    """商品ページを訪問し、除外条件を検証する。

    商品ページで正確な販売価格を取得できなかった場合は棄却する。
    検索結果価格と商品ページ価格が大きく乖離した場合も棄却する。
    """
    url = candidate.get("url")
    if not url:
        return None

    search_price = candidate["price"]  # 検索結果での価格（検証用に保持）

    page = context.new_page()
    try:
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
        time.sleep(random.uniform(1.5, 3.0))

        title_el = page.query_selector("h1, #js_scl_prodNm, .pInfo h1")
        title = title_el.text_content().strip()[:200] if title_el else ""

        if title and is_used_or_excluded(title):
            return None
        if title and _is_accessory_name(product_name, title):
            return None
        if title and _is_model_mismatch(product_name, title):
            print(f"verify: 型番不一致 CSV={product_name[:30]} EC={title[:30]}", file=sys.stderr)
            return None

        info_area = page.query_selector(".pInfo, #js_scl_prodInfo, .productInfo")
        info_text = info_area.text_content() if info_area else ""
        if any(kw in info_text for kw in ["中古", "リユース", "used"]):
            return None

        page_text = page.text_content("body") or ""
        if "販売休止" in page_text or "販売終了" in page_text or "予定数の販売を終了" in page_text:
            return None
        if "在庫あり" in page_text or "在庫残少" in page_text:
            candidate["stock_status"] = "in_stock"
        elif "お取り寄せ" in page_text:
            candidate["stock_status"] = "limited"

        # --- 価格の再取得（商品ページが正） ---
        page_price = None

        # 方法1: 専用セレクタから取得（ポイント表示を避ける）
        for price_sel in ["#js_scl_priceBox", ".pInfo .red", ".productPrice",
                          ".price .num", "[class*='Price'] .num"]:
            price_el = page.query_selector(price_sel)
            if price_el:
                extracted = extract_selling_price(price_el.text_content())
                if extracted:
                    page_price = extracted
                    break

        # 方法2: ページ全体からポイントを除外して取得
        if not page_price:
            page_price = extract_selling_price(page_text)

        # 商品ページで価格が取れなかった場合は信頼できないため棄却
        if not page_price:
            print(f"verify: price not found on page {url}", file=sys.stderr)
            return None

        # 検索結果価格と商品ページ価格の乖離チェック
        if not verify_price_consistency(search_price, page_price):
            print(f"verify: price mismatch search={search_price} page={page_price}", file=sys.stderr)
            return None

        candidate["price"] = page_price

        # ポイント再計算
        pt_match = re.search(r"(\d{1,2})[%％]\s*(?:ポイント|還元)", page_text)
        if pt_match:
            pt_rate = int(pt_match.group(1)) / 100
            candidate["points"] = int(page_price * pt_rate)
        else:
            # ￥付きポイント額を直接取得
            pt_yen = re.search(r"￥([\d,]+)\s*(?:ポイント|円相当)", page_text)
            if pt_yen:
                candidate["points"] = int(pt_yen.group(1).replace(",", ""))
            else:
                candidate["points"] = int(page_price * 0.01)

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
        browser = p.firefox.launch(headless=True, timeout=30000)
        try:
            context = create_stealth_context(browser)
            page = context.new_page()
            page.goto(
                f"https://www.yodobashi.com/?word={encode_query(search_keyword)}",
                timeout=30000,
                wait_until="domcontentloaded",
            )
            time.sleep(random.uniform(3.0, 5.5))

            items = page.query_selector_all(".srcResultItem")

            candidates = []
            for item in items[:5]:
                name_el = item.query_selector("a[href*='/product/']")
                name = name_el.text_content().strip()[:120] if name_el else ""
                if not name:
                    continue

                item_text = item.text_content()

                # 販売価格をポイント額と区別して抽出
                price = extract_selling_price(item_text)
                if not price:
                    continue

                link_el = item.query_selector("a[href*='/product/']")
                href = link_el.get_attribute("href") if link_el else ""
                url = f"https://www.yodobashi.com{href}" if href and not href.startswith("http") else href

                stock_status = "unknown"
                if "在庫あり" in item_text or "在庫残少" in item_text:
                    stock_status = "in_stock"
                elif "お取り寄せ" in item_text:
                    stock_status = "limited"
                elif "販売休止" in item_text or "販売終了" in item_text or "予定数の販売を終了" in item_text:
                    stock_status = "out_of_stock"

                pt_match = re.search(r"(\d{1,2})[%％]\s*(?:ポイント|還元)", item_text)
                pt_rate = int(pt_match.group(1)) / 100 if pt_match else 0.01
                points = int(price * pt_rate)

                if stock_status == "out_of_stock":
                    continue
                if _is_accessory_name(product_name, name):
                    continue
                if _is_model_mismatch(product_name, name):
                    print(f"型番不一致: CSV={product_name[:30]} EC={name[:30]}", file=sys.stderr)
                    continue

                candidates.append({
                    "name": name, "price": price, "shop": "ヨドバシ.com",
                    "url": url, "points": points, "source": "ヨドバシ",
                    "stock_status": stock_status,
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
