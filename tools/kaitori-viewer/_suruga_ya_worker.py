"""駿河屋検索ワーカー（戦略R、サブプロセスとして実行）

JAN検索→ 中古/新品の最安価格を抽出する。レトロゲーム/トレカ/フィギュア向け。
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

jan_code = sys.argv[1]


def _extract_prices(page) -> dict:
    """検索結果ページから新品/中古の最安値を抽出"""
    new_price: int | None = None
    used_price: int | None = None

    # 駿河屋の検索結果カード（item_box, item_list 等）
    cards = page.query_selector_all("div.item, .product, .item_box, .item_list_box")
    for card in cards[:10]:
        text = card.text_content() or ""
        # 「新品」と「中古」のラベル + 価格を抽出
        is_new = "新品" in text or "新品買取" not in text and "中古" not in text
        is_used = "中古" in text or "USED" in text.upper()

        # 価格は ￥1,234 または 1,234円 形式
        prices = re.findall(r"(?:[￥¥]\s*)?(\d{1,3}(?:,\d{3})+|\d{3,6})\s*(?:円)?", text)
        for p in prices:
            try:
                v = int(p.replace(",", ""))
                if 100 <= v <= 1_000_000:
                    if is_new and (new_price is None or v < new_price):
                        new_price = v
                    if is_used and (used_price is None or v < used_price):
                        used_price = v
                    break  # 1カードあたり最初の価格のみ
            except ValueError:
                continue

    return {"new_price": new_price, "used_price": used_price}


def main():
    try:
        from playwright.sync_api import sync_playwright
        from stealth import create_stealth_context, launch_stealth_browser, safe_goto
    except ImportError:
        print(json.dumps({"jan": jan_code, "error": "playwright not installed"}))
        return

    url = f"https://www.suruga-ya.jp/search?search_word={jan_code}"

    try:
        with sync_playwright() as p:
            browser = launch_stealth_browser(p, prefer="chromium")
            context = create_stealth_context(browser)
            page = context.new_page()
            ok = safe_goto(
                page, url,
                warmup_url="https://www.suruga-ya.jp/",
                timeout=20000, max_retries=1,
                post_delay=(1.5, 3.0),
            )
            if not ok:
                print(json.dumps({"jan": jan_code, "error": "access blocked"}))
                browser.close()
                return

            prices = _extract_prices(page)
            browser.close()
            print(json.dumps({"jan": jan_code, **prices}))
    except Exception as e:
        print(json.dumps({"jan": jan_code, "error": str(e)[:200]}))


if __name__ == "__main__":
    main()
