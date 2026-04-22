"""マップカメラ検索ワーカー（カメラ専門、Firefox使用）

マップカメラは Chromium だと ERR_HTTP2_PROTOCOL_ERROR になるため Firefox を使う。
中古品も扱うが買取店ルートは新品前提のため、「中古」を含むカードは除外する。

引数:
  sys.argv[1]: JAN（検索キーワードとして使用）
  sys.argv[2]: 商品名（任意、JAN不発時の代替検索に使用）
"""
import io
import json
import re
import sys
from urllib.parse import quote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from _worker_common import extract_selling_price

jan_code = sys.argv[1]
product_name = sys.argv[2] if len(sys.argv) > 2 else ""


def _similarity_ok(csv_name: str, ec_name: str, threshold: float = 55.0) -> bool:
    if not csv_name:
        return True
    try:
        from rapidfuzz import fuzz
        return fuzz.token_set_ratio(csv_name[:80], ec_name[:80]) >= threshold
    except ImportError:
        csv_tokens = set(re.findall(r"[A-Za-z0-9]{2,}", csv_name.upper()))
        ec_tokens = set(re.findall(r"[A-Za-z0-9]{2,}", ec_name.upper()))
        if not csv_tokens:
            return False
        return len(csv_tokens & ec_tokens) / len(csv_tokens) >= 0.4


def _search_with_keyword(page, keyword: str) -> dict | None:
    """JS で .price 周辺の商品情報を一括抽出"""
    from stealth import safe_goto
    url = f"https://www.mapcamera.com/search?keyword={quote(keyword)}"
    ok = safe_goto(
        page, url,
        warmup_url="https://www.mapcamera.com/",
        timeout=20000, max_retries=1,
        post_delay=(2.0, 4.0),
    )
    if not ok:
        return None

    # page.evaluate で全ての .price について商品情報を取得
    items = page.evaluate("""() => {
        const prices = document.querySelectorAll('.price');
        const result = [];
        for (let i = 0; i < Math.min(20, prices.length); i++) {
            const p = prices[i];
            // 親を辿って最初にリンクを含む要素をカードとする
            let card = p;
            for (let j = 0; j < 8; j++) {
                if (!card.parentElement) break;
                card = card.parentElement;
                const link = card.querySelector('a[href]');
                if (link) {
                    result.push({
                        priceText: p.textContent.trim(),
                        cardText: card.textContent.trim().substring(0, 400),
                        href: link.getAttribute('href') || '',
                    });
                    break;
                }
            }
        }
        return result;
    }""")

    for it in items:
        card_text = it.get("cardText", "")
        price_text = it.get("priceText", "")

        # 中古・アクセサリ除外
        if any(kw in card_text[:300] for kw in ("中古", "USED", "used", "Used", "ジャンク")):
            continue
        if any(kw in card_text[:300] for kw in ("ケース", "フィルター", "充電器", "ストラップ", "予備", "バッテリー")):
            # 本体キーワードが含まれていれば許容
            if not any(kw in card_text[:300] for kw in ("ボディ", "本体", "キット", "ダブルズーム", "レンズキット")):
                continue

        price = extract_selling_price(price_text)
        if not price or price < 1000:
            continue

        # URL
        href = it.get("href", "")
        if href.startswith("/"):
            ec_url = "https://www.mapcamera.com" + href
        elif href.startswith("http"):
            ec_url = href
        else:
            ec_url = ""

        # 商品名（cardText の最初の意味ある行）
        lines = [l.strip() for l in card_text.split("\n") if l.strip()]
        name = next((l for l in lines if len(l) > 10), card_text[:100])[:200]

        # 類似度チェック
        if product_name and not _similarity_ok(product_name, name + " " + card_text[:100]):
            continue

        return {"name": name, "price": price, "url": ec_url}

    return None


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("null")
        return

    try:
        from stealth import create_stealth_context, launch_stealth_browser
    except ImportError:
        print("null")
        return

    # リトライ対応（マップカメラはアクセス不安定、Firefox優先）
    for attempt in range(2):
        try:
            with sync_playwright() as p:
                browser = launch_stealth_browser(p, prefer="firefox")
                context = create_stealth_context(browser)
                page = context.new_page()

                # 1段階: JAN で検索
                data = None
                try:
                    data = _search_with_keyword(page, jan_code)
                except Exception as e:
                    print(f"JAN検索試行{attempt+1}失敗: {e}", file=sys.stderr)

                # 2段階: JANヒットなし & 商品名あり → 商品名検索
                if not data and product_name:
                    try:
                        data = _search_with_keyword(page, product_name[:40])
                    except Exception as e:
                        print(f"商品名検索試行{attempt+1}失敗: {e}", file=sys.stderr)

                browser.close()

                if data:
                    result = {
                        "name": data["name"],
                        "price": data["price"],
                        "shop": "マップカメラ",
                        "url": data["url"],
                        "points": int(data["price"] * 0.02),
                        "source": "マップカメラ",
                        "stock_status": "in_stock",
                    }
                    print(json.dumps(result, ensure_ascii=False))
                    return
                # 結果なしの場合、もう一度試行しない（空）
                if attempt == 0:
                    continue
                print("null")
                return
        except Exception as e:
            print(f"試行{attempt+1}エラー: {e}", file=sys.stderr)
            if attempt == 1:
                print("null")
                return


if __name__ == "__main__":
    main()
