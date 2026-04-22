"""買取店の価格スクレイピング汎用ワーカー（サブプロセス実行）

引数: jan url
出力: JSON {"jan": "...", "price": int} or "null"

既知の買取店ドメインごとに簡易セレクタ＋正規表現フォールバックで価格抽出。
"""
import io
import json
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

jan_code = sys.argv[1]
url = sys.argv[2] if len(sys.argv) > 2 else ""

# ドメインごとのセレクタ候補（表示されている買取価格）
_SITE_SELECTORS = {
    "aboutec.jp": [".price_area", ".price", ".kaitori-price", "[class*='price']"],
    "kaitorishouten-co.jp": [".kaitori-price", ".price", ".entry-price"],
    "kaitori-rudeya.com": [".price", ".item-price", "[class*='price']"],
}


def _extract_buyback_price(text: str) -> int | None:
    """テキストから買取価格（円）を抽出。

    「買取価格」「買取上限」「最大」等の文脈ワード付近の数値を優先。
    """
    if not text:
        return None

    # 優先: 「買取上限」「買取価格」「買取MAX」等の直後
    context_patterns = [
        r"(?:買取上限|買取価格|買取MAX|買取最大|最大買取)[\s:：円¥￥]*(\d{1,3}(?:,\d{3}){1,2})",
        r"(\d{1,3}(?:,\d{3}){1,2})\s*円\s*(?:買取|まで)",
    ]
    candidates = []
    for pat in context_patterns:
        for m in re.finditer(pat, text):
            v = m.group(1).replace(",", "")
            try:
                n = int(v)
                if 1000 <= n <= 9_999_999:
                    candidates.append(n)
            except ValueError:
                pass

    if candidates:
        return max(candidates)

    # フォールバック: body 中の円表記の最大値（送料等を排除するため最小1000円）
    nums = re.findall(r"(?<!\d)(\d{1,3}(?:,\d{3}){1,2})\s*円", text)
    fallback = []
    for v in nums:
        try:
            n = int(v.replace(",", ""))
            if 1000 <= n <= 9_999_999:
                fallback.append(n)
        except ValueError:
            pass
    return max(fallback) if fallback else None


def main():
    if not url or not url.startswith("http"):
        print("null")
        return

    try:
        from playwright.sync_api import sync_playwright
        from stealth import create_stealth_context, launch_stealth_browser, safe_goto
    except ImportError:
        print("null")
        return

    # 買取店ドメインをwarmupURLに指定（サイト別）
    from urllib.parse import urlparse as _uparse
    _parsed = _uparse(url)
    _warmup = f"{_parsed.scheme}://{_parsed.netloc}/"

    try:
        with sync_playwright() as p:
            browser = launch_stealth_browser(p, prefer="chromium")
            context = create_stealth_context(browser)
            page = context.new_page()
            ok = safe_goto(
                page, url,
                warmup_url=_warmup,
                timeout=20000, max_retries=1,
                post_delay=(1.5, 3.0),
            )
            if not ok:
                print("null")
                browser.close()
                return

            # ドメインごとの専用セレクタを試す
            price = None
            for dom, sels in _SITE_SELECTORS.items():
                if dom in url:
                    for sel in sels:
                        el = page.query_selector(sel)
                        if el:
                            p_val = _extract_buyback_price(el.text_content() or "")
                            if p_val:
                                price = p_val
                                break
                    if price:
                        break

            # body全体から抽出
            if not price:
                body = page.text_content("body") or ""
                price = _extract_buyback_price(body)

            browser.close()

            if not price:
                print("null")
                return
            print(json.dumps({"jan": jan_code, "price": price}, ensure_ascii=False))
    except Exception as e:
        print("null")
        print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
