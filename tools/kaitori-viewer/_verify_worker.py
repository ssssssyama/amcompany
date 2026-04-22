"""汎用商品ページ検証ワーカー（サブプロセスとして実行される）

任意のEC商品URLを訪問し、販売価格・除外条件・在庫を検証する。
楽天・Yahoo等のAPI結果を商品ページで裏付けるために使用。

引数: url expected_price
出力: JSON { price, stock_status, name, excluded, reason } or "null"
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
    extract_msrp, extract_selling_price, human_delay, human_like_goto,
    is_accessory, is_used_or_excluded, verify_price_consistency,
)

url = sys.argv[1]
expected_price = int(sys.argv[2]) if len(sys.argv) > 2 else 0

try:
    from playwright.sync_api import sync_playwright
    from stealth import create_stealth_context

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, timeout=15000)
        try:
            context = create_stealth_context(browser)
            page = context.new_page()
            human_like_goto(page, url, timeout=20000)

            page_text = page.text_content("body") or ""

            # 商品名取得
            title_el = page.query_selector("h1, [class*='product'][class*='name'], [class*='item'][class*='name'], title")
            title = ""
            if title_el:
                title = title_el.text_content().strip()[:200]
                # <title> タグのサイト名を除去
                for sep in [" - ", " | ", " ／ ", "｜"]:
                    if sep in title:
                        title = title.split(sep)[0].strip()

            # 除外条件チェック
            if title and is_used_or_excluded(title):
                print(json.dumps({"excluded": True, "reason": "used_or_excluded", "name": title[:120]}, ensure_ascii=False))
                sys.exit(0)

            if title and is_accessory(title):
                print(json.dumps({"excluded": True, "reason": "accessory", "name": title[:120]}, ensure_ascii=False))
                sys.exit(0)

            # 商品説明内の除外表記
            for kw in ["中古品", "アウトレット品", "展示品", "整備済み品", "Amazon Renewed"]:
                if kw in page_text:
                    print(json.dumps({"excluded": True, "reason": kw, "name": title[:120]}, ensure_ascii=False))
                    sys.exit(0)

            # 在庫確認
            stock_status = "unknown"
            if any(kw in page_text for kw in ["販売終了", "品切れ", "在庫なし", "入荷未定", "売り切れ",
                                                "取扱終了", "現在ご購入いただけません"]):
                stock_status = "out_of_stock"
            elif any(kw in page_text for kw in ["カートに入れる", "今すぐ買う", "在庫あり", "ご注文できます"]):
                stock_status = "in_stock"
            elif any(kw in page_text for kw in ["お取り寄せ", "予約", "入荷次第"]):
                stock_status = "limited"

            # 価格取得（ポイント額除外）
            page_price = extract_selling_price(page_text)
            if not page_price:
                # ￥なし「円（税込）」パターン
                tax_match = re.search(r"([\d,]+)\s*円\s*[（(]税込", page_text)
                if tax_match:
                    page_price = int(tax_match.group(1).replace(",", ""))

            # ポイント取得
            points = 0
            pt_pct = re.search(r"(\d{1,2})[%％]\s*(?:ポイント|還元)", page_text)
            if pt_pct and page_price:
                points = int(page_price * int(pt_pct.group(1)) / 100)
            else:
                pt_abs = re.search(r"[￥¥]?([\d,]+)\s*(?:ポイント|円相当)", page_text)
                if pt_abs:
                    points = int(pt_abs.group(1).replace(",", ""))

            # 定価 (MSRP) 抽出: プレミア化検出 (買取 > 定価) に使う
            msrp = extract_msrp(page_text)

            result = {
                "excluded": False,
                "price": page_price,
                "msrp": msrp,
                "stock_status": stock_status,
                "name": title[:120] if title else "",
                "points": points,
                "url": page.url,  # リダイレクト後の実URL
            }

            # 期待価格との整合性チェック
            if expected_price > 0 and page_price:
                result["price_consistent"] = verify_price_consistency(expected_price, page_price)

            print(json.dumps(result, ensure_ascii=False))

        finally:
            browser.close()

except Exception as e:
    print("null")
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
