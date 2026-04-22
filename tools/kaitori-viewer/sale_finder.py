"""セール駆動の逆方向サーチ（戦略B）

楽天・Yahooのランキング/セールAPIからJANリストを取得し、
買取CSVと照合して「セール中かつ買取可能」な商品を優先対象とする。

使い方:
    from sale_finder import find_sale_intersections
    sale_jans = find_sale_intersections(csv_jans_set)

    # 単体テスト
    python sale_finder.py
"""

import logging
import os
import re
import threading
import time
from typing import Iterable

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# 楽天API レート制限: 1リクエスト/秒（Rakuten公式ガイドライン）
# 429 Too Many Requests 対策
_RAKUTEN_API_LOCK = threading.Lock()
_RAKUTEN_LAST_CALL = [0.0]  # mutable box
_RAKUTEN_MIN_INTERVAL = 1.1  # 秒


def _rakuten_rate_limit():
    """楽天APIリクエスト前に 1.1 秒間隔を確保"""
    with _RAKUTEN_API_LOCK:
        elapsed = time.time() - _RAKUTEN_LAST_CALL[0]
        if elapsed < _RAKUTEN_MIN_INTERVAL:
            time.sleep(_RAKUTEN_MIN_INTERVAL - elapsed)
        _RAKUTEN_LAST_CALL[0] = time.time()

load_dotenv()
RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID", "")
RAKUTEN_ACCESS_KEY = os.getenv("RAKUTEN_ACCESS_KEY", "")
RAKUTEN_APP_URL = os.getenv("RAKUTEN_APP_URL", "")  # 登録時のApp URL（Referer必須）
YAHOO_APP_ID = os.getenv("YAHOO_APP_ID", "")


def _is_uuid_format(s: str) -> bool:
    """UUID 形式（新形式キー）か判定"""
    return bool(s) and s.count("-") == 4 and len(s) == 36


# 楽天ウェブサービス 新形式認証専用
# 必須: RAKUTEN_APP_ID (UUID) + RAKUTEN_ACCESS_KEY (pk_...) + RAKUTEN_APP_URL (登録URL)
_RAKUTEN_VALID = (
    _is_uuid_format(RAKUTEN_APP_ID)
    and bool(RAKUTEN_ACCESS_KEY)
    and bool(RAKUTEN_APP_URL)
)

# 新エンドポイント（openapi.rakuten.co.jp）固定
RAKUTEN_SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"

if not _RAKUTEN_VALID:
    if not RAKUTEN_APP_ID:
        logger.warning(
            "RAKUTEN_APP_ID が未設定です。楽天API関連機能（戦略B/I/Q）はスキップされます。"
            "https://webservice.rakuten.co.jp/app/list で新形式キーを取得してください。"
        )
    elif not _is_uuid_format(RAKUTEN_APP_ID):
        logger.warning(
            "RAKUTEN_APP_ID が新形式（UUID）ではありません。"
            "旧形式(19桁)キーは廃止されました。楽天ウェブサービスで新規アプリを作成し "
            "UUID形式の ApplicationID + Access Key を .env に設定してください。"
        )
    elif not RAKUTEN_ACCESS_KEY:
        logger.warning(
            "RAKUTEN_ACCESS_KEY が未設定です。楽天ウェブサービス管理画面の "
            "アプリ詳細で Access Key を確認し .env に設定してください。"
        )
    elif not RAKUTEN_APP_URL:
        logger.warning(
            "RAKUTEN_APP_URL が未設定です。楽天ウェブサービス管理画面で "
            "登録した Application URL と完全一致させて .env に設定してください "
            "（例: https://github.com/）。"
        )


def _build_rakuten_params(extra: dict) -> dict:
    """認証情報付きの楽天APIパラメータを構築（新形式）"""
    return {
        "applicationId": RAKUTEN_APP_ID,
        "accessKey": RAKUTEN_ACCESS_KEY,
        **extra,
    }


def _build_rakuten_headers() -> dict:
    """新形式は Referer 必須（登録時のApp URL と完全一致）"""
    ref = RAKUTEN_APP_URL if RAKUTEN_APP_URL.endswith("/") else RAKUTEN_APP_URL + "/"
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": ref,
        "Origin": ref.rstrip("/"),
    }

# 後方互換: 既存コードの参照用。実際の送信時は _build_rakuten_headers() を使う
RAKUTEN_HEADERS = {
    "Referer": "https://github.com/",
    "Origin": "https://github.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# 楽天IchibaItemSearch: JAN抽出ができないので、キーワード=ジャンル名 + sort=saleで代用
# カメラ/ゲーム/グラボ関連のジャンルキーワード
_RAKUTEN_SALE_KEYWORDS = [
    "デジタル一眼カメラ", "ミラーレスカメラ", "カメラレンズ",
    "Nintendo Switch", "PS5", "プレイステーション5",
    "グラフィックボード", "GPU",
]


def _extract_jan_from_text(text: str) -> str | None:
    """商品名やURLから13桁または8桁のJANコードを抽出"""
    if not text:
        return None
    # 13桁JAN
    m = re.search(r"(?<!\d)(\d{13})(?!\d)", text)
    if m:
        return m.group(1)
    # 8桁JAN
    m = re.search(r"(?<!\d)(\d{8})(?!\d)", text)
    if m:
        return m.group(1)
    return None


def fetch_rakuten_sale_jans(max_per_keyword: int = 30) -> list[str]:
    """楽天市場で「値下げ順」で検索してJANを抽出

    各ジャンルキーワードで上位商品を取得。商品名にJANが含まれていれば抽出。
    """
    if not _RAKUTEN_VALID:
        return []  # 起動時警告済みなのでサイレントにスキップ

    jans: list[str] = []
    seen: set[str] = set()
    headers = _build_rakuten_headers()

    for keyword in _RAKUTEN_SALE_KEYWORDS:
        params = _build_rakuten_params({
            "keyword": keyword,
            "hits": min(max_per_keyword, 30),
            "sort": "-reviewCount",  # レビュー数降順（人気商品 = セール対象になりやすい）
            "availability": 1,
        })
        try:
            _rakuten_rate_limit()
            resp = requests.get(RAKUTEN_SEARCH_URL, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # 新エンドポイントは data.Items が Item 配列を直接返す、
            # 旧エンドポイントは [{Item: {...}}, ...] とラップされた形式
            items_list = data.get("Items", [])
            for item_wrapper in items_list:
                # ラップ形式なら Item キー、直接形式ならそのまま使う
                item = item_wrapper.get("Item", item_wrapper) if isinstance(item_wrapper, dict) else {}
                name = item.get("itemName", "")
                item_code = item.get("itemCode", "")
                item_url = item.get("itemUrl", "")

                # 商品名・itemCode・URL からJAN抽出を試行
                for source in [name, item_code, item_url]:
                    jan = _extract_jan_from_text(source)
                    if jan and jan not in seen:
                        jans.append(jan)
                        seen.add(jan)
                        break
        except (requests.RequestException, ValueError) as e:
            logger.warning("楽天ランキング取得失敗 (%s): %s", keyword, e)

    logger.info("楽天セール検索: %d件のJAN抽出", len(jans))
    return jans


def fetch_yahoo_sale_jans(max_per_keyword: int = 30) -> list[str]:
    """Yahoo!ショッピングでセール商品のJANを取得"""
    if not YAHOO_APP_ID:
        logger.warning("YAHOO_APP_ID が未設定")
        return []

    url = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
    jans: list[str] = []
    seen: set[str] = set()

    for keyword in _RAKUTEN_SALE_KEYWORDS:
        params = {
            "appid": YAHOO_APP_ID,
            "query": keyword,
            "results": min(max_per_keyword, 50),
            "sort": "-review_count",
            "in_stock": "true",
            "condition": "new",
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            for hit in data.get("hits", []):
                jan = hit.get("janCode") or _extract_jan_from_text(hit.get("name", ""))
                if jan and jan not in seen:
                    jans.append(jan)
                    seen.add(jan)
        except (requests.RequestException, ValueError) as e:
            logger.warning("Yahoo セール検索失敗 (%s): %s", keyword, e)

    logger.info("Yahoo セール検索: %d件のJAN抽出", len(jans))
    return jans


def find_sale_intersections(csv_jans: Iterable[str]) -> list[str]:
    """ランキング/セール上位 ∩ 買取CSV のJANを返す"""
    csv_set = set(str(j) for j in csv_jans)
    if not csv_set:
        return []

    all_jans: list[str] = []
    all_jans.extend(fetch_rakuten_sale_jans())
    all_jans.extend(fetch_yahoo_sale_jans())

    # 重複除去しつつ順序保持
    seen: set[str] = set()
    intersection: list[str] = []
    for jan in all_jans:
        if jan in csv_set and jan not in seen:
            intersection.append(jan)
            seen.add(jan)

    logger.info("セール ∩ CSV: %d件", len(intersection))
    return intersection


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # CSVから全JANを取得
    from pathlib import Path
    from csv_loader import load_csv

    CSV_DIR = Path(__file__).resolve().parent.parent.parent
    csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
    if not csv_files:
        print("CSVなし")
        exit(1)

    df = load_csv(str(csv_files[0]))
    csv_jans = set(df["JAN"].tolist())
    print(f"CSV JAN数: {len(csv_jans)}")

    intersection = find_sale_intersections(csv_jans)
    print(f"\n=== セール ∩ CSV ===")
    print(f"該当: {len(intersection)}件")
    for jan in intersection[:20]:
        row = df[df["JAN"] == jan].iloc[0] if len(df[df["JAN"] == jan]) else None
        if row is not None:
            print(f"  {jan}: 買取{row['最高買取価格']:,}円 {row['商品名'][:40]}")
