"""ツクモ検索ワーカー（PC専門、JAN直URL方式）

ツクモは `https://shop.tsukumo.co.jp/goods/{JAN}/` の直URLで商品ページに到達する。
JAN一致は URL で保証される（存在しないJANはトップページにリダイレクトされる）。
"""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from _worker_common import extract_selling_price, is_used_or_excluded

jan_code = sys.argv[1]

# 存在しないJAN時にツクモがリダイレクトする典型的なタイトル（トップページ）
_NOT_FOUND_TITLE_MARKERS = [
    "自作PC・PCパーツが豊富",
    "TSUKUMO",
]


_OUT_OF_STOCK_MARKERS = [
    "在庫なし", "品切れ", "売り切れ", "SOLD OUT",
    "販売終了", "取扱終了", "販売休止", "ご注文できません",
    "入荷待ち", "入荷未定",
]
_LIMITED_STOCK_MARKERS = [
    "在庫わずか", "残りわずか", "お取り寄せ", "予約",
]


def _detect_stock_status(page) -> str:
    """ツクモ商品ページの在庫状況を判定。

    Returns: "out_of_stock" / "limited" / "in_stock"
    """
    # 専用の在庫表示要素（最優先）
    for sel in ["[class*='stock']", ".stock-status", ".itemStock"]:
        el = page.query_selector(sel)
        if el:
            text = (el.text_content() or "").strip()
            if any(kw in text for kw in _OUT_OF_STOCK_MARKERS):
                return "out_of_stock"
            if any(kw in text for kw in _LIMITED_STOCK_MARKERS):
                return "limited"
            if "在庫あり" in text:
                return "in_stock"

    # ボディテキストでのフォールバック判定
    body = page.text_content("body") or ""
    # ネガティブシグナル最優先
    if any(kw in body for kw in _OUT_OF_STOCK_MARKERS):
        return "out_of_stock"
    if any(kw in body for kw in _LIMITED_STOCK_MARKERS):
        return "limited"
    # ポジティブシグナル
    if "在庫あり" in body or "カートに入れる" in body:
        return "in_stock"
    return "unknown"


def main():
    try:
        from playwright.sync_api import sync_playwright
        from stealth import create_stealth_context, launch_stealth_browser, safe_goto
    except ImportError:
        print(json.dumps({"error": "playwright not installed"}))
        return

    url = f"https://shop.tsukumo.co.jp/goods/{jan_code}/"

    try:
        with sync_playwright() as p:
            browser = launch_stealth_browser(p, prefer="chromium")
            context = create_stealth_context(browser)
            page = context.new_page()
            ok = safe_goto(
                page, url,
                warmup_url="https://shop.tsukumo.co.jp/",
                timeout=20000, max_retries=1,
                post_delay=(1.0, 2.5),
            )
            if not ok:
                print("null")
                browser.close()
                return

            title = page.title()

            # 存在しないJAN: トップページ系タイトルで商品詳細ではない
            is_product_page = "｜ツクモ公式通販サイト" in title and "自作PC・PCパーツが豊富" not in title
            if not is_product_page:
                print("null")
                browser.close()
                return

            # 商品名を title から抽出
            product_name = title.split("｜")[0].strip()[:200]

            # 中古・アクセサリ除外
            if is_used_or_excluded(product_name):
                print("null")
                browser.close()
                return

            # 在庫状況判定
            stock_status = _detect_stock_status(page)

            # 価格取得: .price セレクタ
            price = None
            for sel in [".price", ".i_price", "[class*='price']", "strong"]:
                el = page.query_selector(sel)
                if el:
                    text = el.text_content() or ""
                    p_val = extract_selling_price(text)
                    if p_val and p_val >= 1000:
                        price = p_val
                        break

            if not price:
                print("null")
                browser.close()
                return

            points = int(price * 0.01)

            result = {
                "name": product_name,
                "price": price,
                "shop": "ツクモ",
                "url": url,
                "points": points,
                "source": "ツクモ",
                "stock_status": stock_status,
            }
            browser.close()
            print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        print("null")
        print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
