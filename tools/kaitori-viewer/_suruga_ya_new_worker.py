"""駿河屋 新品専用ワーカー（買取店ルート向け、中古厳格除外）

JAN検索 → .item_box の最初のカードから「新品：￥XXX」のみを抽出。
中古品・品切れ・定価のみ表示は全て null を返す。

呼び出し規約:
    sys.argv[1]: JAN

出力:
    JSON {name, price, shop, url, points, source, stock_status} または "null"

設計:
- JAN一致検証: 駿河屋の JAN検索は厳密（非マッチ時は0件 or 無関係商品）
  よって商品名類似度チェックは省略し、価格マーカー「新品：」存在のみで安全側判定
- 「中古：」のみで「新品：」がないカードは null（中古のみ在庫＝買取店ルート不適）
- 「品切れ」を含むカードは null（新品在庫切れ）
- 「定価：」は原価表示のため価格として採用しない
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

jan_code = sys.argv[1]

# 新品価格のパターン: 「新品：￥12,345」「新品：12,345円」等
_NEW_PRICE_PATTERN = re.compile(r"新品[：:]\s*[￥¥]?\s*([\d,]+)\s*円?")
# 中古価格のパターン（判定用）
_USED_ONLY_MARKERS = ("中古：", "USED：")
# 在庫切れマーカー
_OUT_OF_STOCK_MARKERS = ("品切れ", "販売終了", "取扱終了", "在庫なし")
# 除外対象キーワード（商品名ベース、中古・ジャンク等）
_NAME_EXCLUDE = ("中古", "JUNK", "ジャンク", "難あり", "訳あり")


def _extract_new_price(text: str) -> int | None:
    """テキストから新品価格を抽出（なければ None）"""
    m = _NEW_PRICE_PATTERN.search(text)
    if not m:
        return None
    try:
        v = int(m.group(1).replace(",", ""))
        if 100 <= v <= 10_000_000:
            return v
    except ValueError:
        pass
    return None


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("null")
        return

    url = f"https://www.suruga-ya.jp/search?search_word={jan_code}"

    try:
        from stealth import create_stealth_context, launch_stealth_browser, safe_goto
    except ImportError:
        print("null")
        return

    try:
        with sync_playwright() as p:
            browser = launch_stealth_browser(p, prefer="chromium")
            context = create_stealth_context(browser)
            page = context.new_page()
            ok = safe_goto(
                page, url,
                warmup_url="https://www.suruga-ya.jp/",
                timeout=30000, max_retries=1,
            )
            if not ok:
                print("null")
                browser.close()
                return

            # 最初の .item_box を検索
            box = page.query_selector(".item_box")
            if not box:
                print("null")
                browser.close()
                return

            full_text = (box.text_content() or "").strip()

            # 品切れ判定（最優先）
            if any(kw in full_text for kw in _OUT_OF_STOCK_MARKERS):
                print("null")
                browser.close()
                return

            # 商品名取得
            name_el = box.query_selector(".product-name")
            name = (name_el.text_content() or "").strip()[:200] if name_el else ""

            # 商品名ベースの中古・ジャンク除外
            if any(kw in name for kw in _NAME_EXCLUDE):
                print("null")
                browser.close()
                return

            # 価格ブロック取得
            price_el = box.query_selector(".item_price")
            price_text = (price_el.text_content() or "") if price_el else full_text

            # 新品価格抽出
            new_price = _extract_new_price(price_text)
            if not new_price:
                # 「新品：」マーカーがない → 中古のみ or 価格未取得 → 除外
                print("null")
                browser.close()
                return

            # 商品URL取得
            link_el = box.query_selector("a[href*='product/detail']")
            product_url = link_el.get_attribute("href") if link_el else url
            if product_url and product_url.startswith("/"):
                product_url = "https://www.suruga-ya.jp" + product_url

            points = int(new_price * 0.01)
            result = {
                "name": name or f"JAN:{jan_code}",
                "price": new_price,
                "shop": "駿河屋",
                "url": product_url or url,
                "points": points,
                "source": "駿河屋",
                "stock_status": "in_stock",
            }
            browser.close()
            print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        print("null")
        print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
