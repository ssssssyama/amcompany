"""メルカリ出品数カウントワーカー（サブプロセスとして実行される）

軽量版：価格は取らず、検索結果の件数のみ取得する。
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

jan_code = sys.argv[1]


def _extract_count(page) -> int:
    """メルカリ検索結果の総件数を抽出する（売却済み除外）"""
    # 1) 件数表示のテキストから抽出
    for sel in [
        "[data-testid='search-result-head']",
        "mer-text.merTypographyTitleMedium",
        "p.merText",
    ]:
        el = page.query_selector(sel)
        if not el:
            continue
        text = el.text_content() or ""
        m = re.search(r"(\d{1,3}(?:,\d{3})*)\s*件", text)
        if m:
            return int(m.group(1).replace(",", ""))

    # 2) 商品カードの数をカウント（フォールバック）
    cards = page.query_selector_all("[data-testid='item-cell'], li.merListItem")
    return len(cards)


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"jan": jan_code, "count": -1, "error": "playwright not installed"}))
        return

    # 売却済みを除外（on_sale=true）
    url = f"https://jp.mercari.com/search?keyword={jan_code}&status=on_sale"

    try:
        from stealth import create_stealth_context, launch_stealth_browser, safe_goto
    except ImportError:
        print(json.dumps({"jan": jan_code, "count": -1, "error": "stealth not importable"}))
        return

    try:
        with sync_playwright() as p:
            browser = launch_stealth_browser(p, prefer="chromium")
            context = create_stealth_context(browser)
            page = context.new_page()
            ok = safe_goto(
                page, url,
                warmup_url="https://jp.mercari.com/",
                timeout=20000, max_retries=1,
                post_delay=(1.5, 3.0),
            )
            if not ok:
                print(json.dumps({"jan": jan_code, "count": -1, "error": "access blocked"}))
                browser.close()
                return

            count = _extract_count(page)
            browser.close()
            print(json.dumps({"jan": jan_code, "count": count}))
    except Exception as e:
        print(json.dumps({"jan": jan_code, "count": -1, "error": str(e)[:200]}))


if __name__ == "__main__":
    main()
