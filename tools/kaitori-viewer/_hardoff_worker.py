"""ハードオフネットモール検索ワーカー（中古特化、サブプロセス実行）

ハードオフは中古品を扱うため、`is_used_or_excluded` の中古フィルタを
適用しない（既存の Amazon/ヨドバシワーカーとは異なる挙動）。

商品ごとに在庫1個（ユニーク）なので、注文時の在庫切れリスクが低い。
無在庫転売向けの仕入先として有用。
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from _worker_common import (
    ACCESSORY_KEYWORDS, extract_selling_price,
)

jan_code = sys.argv[1]


def _is_accessory(name: str) -> bool:
    name_lower = name.lower()
    return any(kw.lower() in name_lower for kw in ACCESSORY_KEYWORDS)


def _detect_stock_status(text: str) -> str:
    """商品テキストから在庫状態を判定"""
    if any(kw in text for kw in ("売約済", "売り切れ", "売却済", "完売", "SOLD OUT")):
        return "out_of_stock"
    if any(kw in text for kw in ("商談中", "取り置き")):
        return "limited"
    return "in_stock"


def _extract_condition_rank(text: str) -> str | None:
    """商品状態ランク（A/B/C等）を抽出"""
    m = re.search(r"(?:状態|ランク|商品状態)[:：\s]*([A-S])", text)
    if m:
        return m.group(1).upper()
    return None


def _card_contains_jan(card, jan: str) -> bool:
    """商品カードまたは商品詳細ページのURLに JAN が含まれるか確認。

    ハードオフは検索ヒット0件でも新着商品30件を返すため、
    JANで本当にマッチしているかをカード単位で確認する必要がある。
    """
    if not jan:
        return False
    text = card.text_content() or ""
    if jan in text:
        return True
    # data属性やaltテキストもチェック
    html = card.inner_html() or ""
    return jan in html


def _extract_first_card_data(page, jan: str) -> dict | None:
    """検索結果の最初の有効商品カードから情報を抽出（JANマッチカードのみ）

    2026年春以降の DOM 変更:
    - カード外殻は `div.item-infowrap`（旧: `div.itemcolmn_item`）
    - 旧セレクタはフォールバックとして残す
    """
    cards = page.query_selector_all("div.item-infowrap, div.itemcolmn_item")

    for card in cards[:30]:
        text = card.text_content() or ""
        if not text or len(text) < 10:
            continue

        # JANマッチを必須化（新着代用商品を除外）
        if not _card_contains_jan(card, jan):
            continue

        # アクセサリ除外
        if _is_accessory(text[:200]):
            continue

        # 売り切れ商品はスキップ
        stock = _detect_stock_status(text)
        if stock == "out_of_stock":
            continue

        # 価格抽出（.item-price から優先）
        price_el = card.query_selector(".item-price, [class*='price']")
        price = None
        if price_el:
            price = extract_selling_price(price_el.text_content() or "")
        if not price:
            price = extract_selling_price(text)
        if not price or price < 100:
            continue

        # リンク取得
        link_el = card.query_selector("a[href*='/product/']")
        url = ""
        if link_el:
            href = link_el.get_attribute("href") or ""
            if href.startswith("/"):
                url = "https://netmall.hardoff.co.jp" + href
            elif href.startswith("http"):
                url = href

        # 商品名（itemcolmn_item の最初の50文字を商品名として使用、価格部を除く）
        name_text = text.replace(price_el.text_content() if price_el else "", "")
        name = " ".join(name_text.split())[:120]

        return {
            "name": name,
            "price": price,
            "url": url,
            "stock_status": stock,
            "condition_rank": _extract_condition_rank(text),
        }

    return None


def main():
    try:
        from playwright.sync_api import sync_playwright
        from stealth import create_stealth_context, launch_stealth_browser, safe_goto
    except ImportError:
        print(json.dumps({"jan": jan_code, "error": "playwright not installed"}))
        return

    url = f"https://netmall.hardoff.co.jp/search/?q={jan_code}"

    try:
        with sync_playwright() as p:
            browser = launch_stealth_browser(p, prefer="chromium")
            context = create_stealth_context(browser)
            page = context.new_page()
            ok = safe_goto(
                page, url,
                warmup_url="https://netmall.hardoff.co.jp/",
                timeout=20000, max_retries=1,
                post_delay=(1.5, 3.0),
            )
            if not ok:
                print("null")
                browser.close()
                return

            data = _extract_first_card_data(page, jan_code)
            browser.close()

            if not data:
                print("null")
                return

            result = {
                "name": data["name"],
                "price": data["price"],
                "shop": "ハードオフネットモール",
                "url": data["url"],
                "points": 0,
                "source": "ハードオフ",
                "stock_status": data["stock_status"],
                "condition": "used",
                "condition_rank": data.get("condition_rank"),
            }
            print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        print("null")
        print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
