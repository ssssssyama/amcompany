"""ヤフオク落札相場ワーカー（戦略J、サブプロセスとして実行）

closedsearch から過去の落札価格を抽出し、中央値を返す。bot対策のため
User-Agentランダム化と短い待機を入れる。
"""
import io
import json
import random
import re
import statistics
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

jan_code = sys.argv[1]

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def _extract_winning_prices(page) -> list[int]:
    """ヤフオク落札済み一覧から価格を抽出"""
    prices: list[int] = []
    # 商品カード（プロダクト一覧）
    items = page.query_selector_all(".Product, .Result__list li, .ProductItem")
    for it in items[:30]:
        text = it.text_content() or ""
        # 「落札 1,234円」「現在価格 1,234円」などのパターン
        m = re.search(r"(?:落札|現在|即決)?\s*(\d{1,3}(?:,\d{3})+|\d{3,7})\s*円", text)
        if m:
            try:
                v = int(m.group(1).replace(",", ""))
                if 100 <= v <= 5_000_000:
                    prices.append(v)
            except ValueError:
                continue
    return prices


def main():
    try:
        from playwright.sync_api import sync_playwright
        from stealth import create_stealth_context, launch_stealth_browser, safe_goto
    except ImportError:
        print(json.dumps({"jan": jan_code, "error": "playwright not installed"}))
        return

    url = f"https://auctions.yahoo.co.jp/closedsearch/closedsearch?p={jan_code}&fixed=1&exflg=1"

    try:
        with sync_playwright() as p:
            browser = launch_stealth_browser(p, prefer="chromium")
            context = create_stealth_context(
                browser,
                extra_http_headers={"Referer": "https://auctions.yahoo.co.jp/"},
            )
            page = context.new_page()
            ok = safe_goto(
                page, url,
                warmup_url="https://auctions.yahoo.co.jp/",
                timeout=20000, max_retries=1,
                post_delay=(2.0, 4.0),
            )
            if not ok:
                print(json.dumps({"jan": jan_code, "error": "access blocked"}))
                browser.close()
                return

            prices = _extract_winning_prices(page)
            browser.close()

            if len(prices) < 3:
                print(json.dumps({"jan": jan_code, "median": None, "count": len(prices)}))
                return

            median = int(statistics.median(prices))
            print(json.dumps({"jan": jan_code, "median": median, "count": len(prices)}))
    except Exception as e:
        print(json.dumps({"jan": jan_code, "error": str(e)[:200]}))


if __name__ == "__main__":
    main()
