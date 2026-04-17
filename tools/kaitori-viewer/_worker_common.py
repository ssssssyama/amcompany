"""ワーカー共通の除外キーワード・ユーティリティ"""

import random
import re
import time
from urllib.parse import parse_qs as _parse_qs
from urllib.parse import quote as _url_quote
from urllib.parse import unquote as _url_unquote
from urllib.parse import urlparse as _urlparse

# 中古・品質問題
USED_KEYWORDS = [
    "中古", "used", "ジャンク", "訳あり", "わけあり", "難あり", "傷あり",
    "箱なし", "本体のみ", "リファービッシュ", "refurbished", "再生品",
    "アウトレット", "キズ", "きず", "開封済み", "展示品",
    "整備済み", "renewed", "認定済み", "certified refurbished",
    "B級品", "B品", "返品", "デモ機", "モック",
    "サンプル品", "試供品", "動作未確認", "未検品",
    "欠品", "付属品欠品", "保証なし", "保証書なし",
    "並行輸入", "海外版", "海外モデル", "import",
    "非正規品", "非純正", "コピー品", "模倣品", "ノーブランド",
]

# 非商品（保証・レンタル等）
EXCLUDED_KEYWORDS = [
    "まごころ長期修理保証", "長期修理保証", "延長保証", "保証プラン",
    "レンタル", "rental", "貸出", "リース",
    "店頭のみ", "店頭販売", "店頭受取", "店舗限定", "店頭限定",
    "ふるさと納税", "クーポン", "ギフト券", "商品券",
    "法人向け", "業務用", "セット販売のみ",
]

# アクセサリ・部品
ACCESSORY_KEYWORDS = [
    "ケース", "カバー", "フィルム", "保護", "シール",
    "充電器", "充電ケーブル", "ケーブル", "アダプタ", "アダプター",
    "交換用", "替え", "替刃", "フィルター", "対応", "専用",
    "互換", "汎用", "バッテリー", "電池", "パーツ", "部品",
    "付属品", "カートリッジ", "ノズル", "ブラシ", "ヘッド",
    "リフィル", "詰め替え", "スプール", "スリーブ",
    # カメラ関連アクセサリ
    "レンズキャップ", "ボディキャップ", "レンズフード", "レンズペン",
    "液晶保護", "スクリーンプロテクター", "アイカップ", "アイピース",
    "リモートコード", "レリーズ", "グリップベルト",
    "カメラバッグ", "カメラポーチ", "ショルダーストラップ",
    # ゲーム関連アクセサリ
    "コントローラー", "コントローラ", "ヘッドセット", "充電スタンド",
]

MAX_VERIFY = 3  # 商品ページ検証の最大試行数


def is_used_or_excluded(name: str) -> bool:
    """商品名が中古品・除外対象かどうかを判定する"""
    nl = name.lower()
    return any(k in nl for k in USED_KEYWORDS) or any(k in name for k in EXCLUDED_KEYWORDS)


def is_accessory(name: str) -> bool:
    """商品名がアクセサリ・部品かどうかを判定する"""
    nl = name.lower()
    return any(kw in nl for kw in ACCESSORY_KEYWORDS)


def extract_yen_price(text: str) -> int | None:
    """テキストから ￥ 付き価格を抽出し、最小値を返す（ポイント額は除外しない簡易版）"""
    matches = re.findall(r"[￥¥](\d{1,3}(?:,\d{3}){1,2})", text)
    prices = [v for v in (int(m.replace(",", "")) for m in matches) if v >= 1000]
    return min(prices) if prices else None


def extract_selling_price(text: str) -> int | None:
    """テキストから販売価格を抽出する（ポイント額を除外）

    量販店ECでは販売価格とポイント還元額の両方に ￥ マークが付く。
    ヨドバシ等では「￥319,00031,900」のように価格とポイント額が
    スペースなしで連結されるため、厳密な桁区切りパターンで抽出する。
    """
    # 厳密なカンマ区切り価格パターン: ￥1,000 〜 ￥9,999,999
    _PRICE_PATTERN = r"[￥¥](\d{1,3}(?:,\d{3}){1,2})"

    # ポイント額を特定して除外
    point_values = set()
    for m in re.finditer(_PRICE_PATTERN + r"\s*(?:ポイント|円相当)", text):
        point_values.add(m.group(1))

    # ￥付き数値を順番に走査し、ポイント額でない最初の有効価格を返す
    for m in re.finditer(_PRICE_PATTERN, text):
        raw = m.group(1)
        if raw in point_values:
            continue
        price = int(raw.replace(",", ""))
        if price >= 1000:
            return price

    # フォールバック: 「27,800 円(税込)」形式（コジマ等、￥マークなし）
    tax_match = re.search(r"(\d{1,3}(?:,\d{3}){1,2})\s*円\s*[（(]税込", text)
    if tax_match:
        price = int(tax_match.group(1).replace(",", ""))
        if price >= 1000:
            return price

    return None


def verify_price_consistency(search_price: int, page_price: int, max_ratio: float = 1.5) -> bool:
    """検索結果価格と商品ページ価格の整合性を確認する"""
    if search_price <= 0 or page_price <= 0:
        return True
    ratio = page_price / search_price
    return (1 / max_ratio) <= ratio <= max_ratio


def encode_query(text: str) -> str:
    """URLクエリパラメータ用にエンコードする"""
    return _url_quote(text, safe="")


def decode_kakaku_redirect(kakaku_url: str) -> str:
    """価格.comの遷移URLから実店舗URLをデコードする

    パターン1: kakaku.com/ksearch/jump/?u={encoded_url}
    パターン2: kakaku.com/forwarder/forward.aspx?...&Url={encoded_url}
    """
    try:
        parsed = _urlparse(kakaku_url)
        params = _parse_qs(parsed.query)
        for key in ("u", "Url", "url"):
            if key in params:
                return _url_unquote(params[key][0])
    except Exception:
        pass
    return kakaku_url


# ---------------------------------------------------------------------------
# bot対策: 人間的な操作をシミュレートするユーティリティ
# ---------------------------------------------------------------------------

def human_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    """人間的なランダム待機"""
    time.sleep(random.uniform(min_sec, max_sec))


def human_scroll(page, steps: int = 3):
    """人間的なスクロール（段階的に下へスクロール）"""
    for _ in range(steps):
        scroll_amount = random.randint(200, 500)
        page.mouse.wheel(0, scroll_amount)
        time.sleep(random.uniform(0.3, 0.8))


def human_mouse_move(page):
    """ランダムな位置にマウスを移動"""
    vp = page.viewport_size or {"width": 1920, "height": 1080}
    x = random.randint(100, vp["width"] - 100)
    y = random.randint(100, vp["height"] - 100)
    page.mouse.move(x, y)
    time.sleep(random.uniform(0.1, 0.3))


def human_like_goto(page, url: str, timeout: int = 20000):
    """人間的なページ遷移（リファラー設定 + 段階的読み込み待機 + スクロール）"""
    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
    except Exception:
        # networkidle にフォールバック
        page.goto(url, timeout=timeout, wait_until="commit")

    human_delay(1.5, 3.5)
    human_mouse_move(page)
    human_scroll(page, steps=random.randint(1, 3))
    human_delay(0.5, 1.5)
