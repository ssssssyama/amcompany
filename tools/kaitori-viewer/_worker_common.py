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
    # 付属品無し・バリアント違い（買取CSVの本体キット価格と EC 単体価格のミスマッチ防止）
    # 例: Insta360 GO 3S「カメラ単体」版は Action Pod 別売で本体 kit とは別商品
    "カメラ単体", "ボディのみ", "ボディ単体", "body only",
    "アクションポッド別売", "action pod別売", "充電器別売", "充電器なし",
    "アクセサリー別売", "本体単体", "単体モデル",
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


# 価格として誤検出すべきでない文脈（送料閾値・クーポン額・ポイント・割引額・手数料等）
# これらのパターンに該当する数値は販売価格ではないので除外
# 注意: 「N円 キーワード」のようにスペースで隔てたパターンは、商品価格の直後に
#        別要素が来るケース（例「694,620円 ポイント 6,946円相当」）で商品価格まで
#        誤除外してしまうため採用しない。キーワード直結（"円相当"、"円OFF"等）のみ除外。
_NON_PRICE_CONTEXT_PATTERNS = [
    re.compile(r"(\d{1,3}(?:,\d{3}){0,2})\s*円\s*以上"),       # 3,000円以上送料無料
    re.compile(r"(\d{1,3}(?:,\d{3}){0,2})\s*円\s*以下"),       # ○○円以下
    re.compile(r"(\d{1,3}(?:,\d{3}){0,2})\s*円(?:OFF|off|引き|割引|値引き|引)"),  # 500円OFF (直結)
    re.compile(r"(\d{1,3}(?:,\d{3}){0,2})\s*円(?:相当|分|還元|戻)"),  # 500円相当・円分・円還元 (直結)
    re.compile(r"(?:送料|手数料|配送料|中継料|加算料金|取付料|延長保証|保証料|税金)"
               r"[\s:::として一律別途追加約]{0,10}(\d{1,3}(?:,\d{3}){0,2})\s*円"),  # 送料500円、中継料として一律3,000円
    re.compile(r"(?:ポイント|還元|付与)[\s::]*(?:[￥¥])?(\d{1,3}(?:,\d{3}){0,2})\s*円?(?!\d)"),  # ポイント500円
    # 「一律N円」「別途N円」「追加N円」のような付帯費用（送料と文脈ワードが離れている場合の補完）
    re.compile(r"(?:一律|別途|追加|最大)\s*(\d{1,3}(?:,\d{3}){0,2})\s*円"),
    # 希望小売価格・定価・通常価格・参考価格（実際の販売価格とは異なる、二重価格表示の元値）
    re.compile(r"(?:希望小売価格|メーカー希望|参考価格|定価|通常価格|標準価格|旧価格|元値|割引前|セール前)"
               r"[\s:：]*(?:[￥¥])?(\d{1,3}(?:,\d{3}){0,2})\s*円?"),
    # 単価・○○あたりの価格（スペック表の単位価格、テレビ1インチあたり・コピー1枚あたり等）
    # 例: 「1V型(インチ)あたりの価格￥3,104」「1枚あたり￥12」「1個あたり500円」
    # HTMLタグ混入に対応するため、ラベルと価格の間は「数値・円・￥以外」の文字を最大30字まで許容
    re.compile(r"(?:あたりの価格|単価|1(?:V型|インチ|枚|個|本|袋|回|㎡|m2)あたり|[一1]\s*(?:V型|インチ|枚|個|本|袋|回))"
               r"[^￥¥円\d]{0,30}?(?:[￥¥])?(\d{1,3}(?:,\d{3}){0,2})\s*円?"),
]


def _collect_excluded_values(text: str) -> set[str]:
    """販売価格として採用すべきでない値を集合として返す（後方互換、位置情報は失われる）"""
    positions = _collect_excluded_positions(text)
    # 該当テキストから値を再抽出
    values = set()
    for (start, end) in positions:
        seg = text[start:end]
        # 数値+カンマのみを取り出す
        m = re.search(r"\d{1,3}(?:,\d{3}){0,2}", seg)
        if m:
            values.add(m.group())
    return values


def _collect_excluded_positions(text: str) -> set[tuple[int, int]]:
    """除外対象値のテキスト内位置（文字オフセット）を返す。

    同じ値が「希望小売価格」と「販売価格」の両方に出るケース
    （例: メーカー希望小売価格27,280円 → 27,280円）で、
    希望小売価格のテキスト位置だけ除外し、別の位置の同値は残すため
    位置ベースで管理する。
    """
    positions: set[tuple[int, int]] = set()
    for pat in _NON_PRICE_CONTEXT_PATTERNS:
        for m in pat.finditer(text):
            positions.add(m.span(1))  # キャプチャグループ1（数値部）の位置
    return positions


def extract_selling_price(text: str) -> int | None:
    """テキストから販売価格を抽出する（ポイント額・送料閾値・クーポン額を除外）

    量販店ECでは販売価格とポイント還元額の両方に ￥ マークが付く。
    ヨドバシ等では「￥319,00031,900」のように価格とポイント額が
    スペースなしで連結されるため、厳密な桁区切りパターンで抽出する。
    Yahoo Shopping店舗では「3,000円以上送料無料」のような文言で
    商品価格以外の金額が混入するため、文脈で除外する。
    """
    if not text:
        return None

    # <script>内のJSONに埋め込まれた \u003c 等のunicodeエスケープを実文字にデコード
    # （Yahoo Shopping等では spec テーブルのラベルと価格の間に \u003c/th\u003e\u003ctd\u003e
    #  が挿入され、除外パターンの距離判定を妨害するため）
    if "\\u00" in text:
        text = re.sub(
            r"\\u([0-9a-fA-F]{4})",
            lambda m: chr(int(m.group(1), 16)),
            text,
        )

    # 厳密なカンマ区切り価格パターン: ￥1,000 〜 ￥9,999,999
    _PRICE_PATTERN = r"[￥¥](\d{1,3}(?:,\d{3}){1,2})"

    # 除外対象の「テキスト内位置」を取得（同じ値でも位置が違えば別扱い）
    excluded_positions = _collect_excluded_positions(text)
    # ￥付き「円相当」（ポイント額）の位置も除外
    for m in re.finditer(_PRICE_PATTERN + r"\s*円相当", text):
        excluded_positions.add(m.span(1))

    def _is_excluded_position(span: tuple[int, int]) -> bool:
        """マッチ位置が除外位置と一致するか判定"""
        if span in excluded_positions:
            return True
        # 位置が完全一致でなくても、除外位置と重なる場合も除外（正規表現の終端位置違いに対応）
        for (es, ee) in excluded_positions:
            # 中心（数値部分）が重なるなら除外扱い
            if es <= span[0] < ee or span[0] <= es < span[1]:
                return True
        return False

    # ￥付き数値を順番に走査し、除外位置でない最初の有効価格を返す
    for m in re.finditer(_PRICE_PATTERN, text):
        if _is_excluded_position(m.span(1)):
            continue
        price = int(m.group(1).replace(",", ""))
        if price >= 1000:
            return price

    # フォールバック階層:
    # F1: 文脈ワード付き価格（「価格 128,920円」）— 主商品の価格として信頼性が高い
    # F2: 税込付き価格（「128,920円（税込）」）— F1 と同等に信頼
    # F3: 単独「N円」— 関連商品や比較表の価格も混入するため、F1/F2 が全く無い時のみ使う
    #
    # Yahoo Shopping のように主商品が「価格 N円」でラベル付きで表示され、
    # ページ内に関連商品の 185,500円 等が混入するケースで、max(全体) だと
    # 関連商品が採用されてしまうのを防ぐため、ラベル付き候補を優先する。

    labeled_candidates: list[int] = []

    # F1: 文脈ワード付き
    for m in re.finditer(
        r"(?:販売価格|商品価格|価格|セール価格|税込価格|本体価格)[\s::]*(\d{1,3}(?:,\d{3}){1,2})\s*円",
        text,
    ):
        if _is_excluded_position(m.span(1)):
            continue
        p_val = int(m.group(1).replace(",", ""))
        if 1000 <= p_val <= 9_999_999:
            labeled_candidates.append(p_val)

    # F2: N円（税込）
    for m in re.finditer(r"(\d{1,3}(?:,\d{3}){1,2})\s*円\s*[（(]税込", text):
        if _is_excluded_position(m.span(1)):
            continue
        p_val = int(m.group(1).replace(",", ""))
        if 1000 <= p_val <= 9_999_999:
            labeled_candidates.append(p_val)

    if labeled_candidates:
        return max(labeled_candidates)

    # F3: ラベル無し単独「N円」— JSON variation 価格（"price":"255,200円"）は除外
    bare_candidates: list[int] = []
    for m in re.finditer(r"(?<!\d)(\d{1,3}(?:,\d{3}){1,2})\s*円(?!相当)(?!\s*分)", text):
        if _is_excluded_position(m.span(1)):
            continue
        pos = m.start(1)
        if pos > 0 and text[pos - 1] in ('"', "'"):
            continue
        p_val = int(m.group(1).replace(",", ""))
        if 1000 <= p_val <= 9_999_999:
            bare_candidates.append(p_val)

    if bare_candidates:
        return max(bare_candidates)

    return None


# 定価 (MSRP: Manufacturer's Suggested Retail Price) 抽出パターン
# 「希望小売価格」「メーカー希望小売価格」「定価」「参考価格」等のラベル直後の価格を取得
_MSRP_PATTERNS = [
    re.compile(
        r"(?:メーカー希望小売価格|希望小売価格|標準価格|参考価格|定価|通常価格)"
        r"[\s:：(（]*(?:[￥¥])?(\d{1,3}(?:,\d{3}){1,2})\s*円?"
    ),
    re.compile(
        r"(?:MSRP|List\s*Price|Retail\s*Price|RRP)"
        r"[\s:：$]*(?:[￥¥])?(\d{1,3}(?:,\d{3}){1,2})\s*円?",
        re.IGNORECASE,
    ),
]


def extract_msrp(text: str) -> int | None:
    """テキストから定価（メーカー希望小売価格）を抽出する

    1,000円〜10,000,000円の範囲で、最も高値を返す
    （商品ページに複数の関連商品の定価が混在する場合、最も高い値=本体と推定）

    Returns:
        定価（円）または None
    """
    if not text:
        return None
    # JSON エスケープ除去（Yahoo Shopping店舗のJSON埋込対策）
    if "\\u00" in text:
        text = re.sub(
            r"\\u([0-9a-fA-F]{4})",
            lambda m: chr(int(m.group(1), 16)),
            text,
        )
    candidates: list[int] = []
    for pat in _MSRP_PATTERNS:
        for m in pat.finditer(text):
            try:
                v = int(m.group(1).replace(",", ""))
                if 1000 <= v <= 10_000_000:
                    candidates.append(v)
            except ValueError:
                continue
    if not candidates:
        return None
    # 最頻値よりは最大値が本体の定価である可能性が高い
    return max(candidates)


def verify_price_consistency(search_price: int, page_price: int, max_ratio: float = 1.5) -> bool:
    """検索結果価格と商品ページ価格の整合性を確認する"""
    if search_price <= 0 or page_price <= 0:
        return True
    ratio = page_price / search_price
    return (1 / max_ratio) <= ratio <= max_ratio


# 戦略K: 在庫数表示パターン（商品名・説明文から「残り3点」等を抽出）
_STOCK_NUMBER_PATTERNS = [
    re.compile(r"残り\s*(\d{1,2})\s*[点個本台枚セット]"),
    re.compile(r"ラスト\s*(\d{1,2})\s*[点個本台枚]?"),
    re.compile(r"在庫\s*(\d{1,2})\s*[点個本台枚]"),
    re.compile(r"のこり\s*(\d{1,2})\s*[点個本]"),
]


def extract_stock_number(text: str) -> int | None:
    """商品名・説明文から在庫数を抽出（戦略K）

    Args:
        text: 商品名や説明文

    Returns:
        抽出した在庫数（1-99）。見つからなければ None
    """
    if not text:
        return None
    for pat in _STOCK_NUMBER_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                n = int(m.group(1))
                if 1 <= n <= 99:
                    return n
            except (ValueError, IndexError):
                continue
    # 「残りわずか」「ラスト」のみは便宜的に5扱い
    if any(kw in text for kw in ("残りわずか", "残わずか", "在庫わずか", "ラスト1点")):
        return 5
    return None


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
