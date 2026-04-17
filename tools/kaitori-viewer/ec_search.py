"""楽天・Yahoo APIでEC最安値を取得する"""

import difflib
import logging
import os
import random
import re as _re
import threading
import time

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID", "")
RAKUTEN_ACCESS_KEY = os.getenv("RAKUTEN_ACCESS_KEY", "")
YAHOO_APP_ID = os.getenv("YAHOO_APP_ID", "")

_MAX_RETRIES = 1
_RETRY_DELAY = 3


def _get_with_retry(url: str, params: dict, headers: dict | None = None) -> requests.Response | None:
    """リトライ付きGETリクエスト"""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp
        except requests.HTTPError as e:
            logger.warning("HTTP %s: %s", e.response.status_code, url[:60])
            if e.response.status_code == 429 and attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY)
                continue
            return None
        except requests.RequestException as e:
            if attempt < _MAX_RETRIES:
                logger.info("通信エラー、リトライ中... (%s)", url[:60])
                time.sleep(_RETRY_DELAY)
                continue
            logger.warning("通信エラー: %s (%s)", e, url[:60])
            return None
    return None

RAKUTEN_SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"
RAKUTEN_HEADERS = {
    "Referer": "https://github.com/",
    "Origin": "https://github.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
YAHOO_SEARCH_URL = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"

RAKUTEN_POINT_RATE = 0.01

_USED_KEYWORDS = [
    "中古", "used", "ジャンク", "訳あり", "わけあり",
    "難あり", "傷あり", "箱なし", "本体のみ",
    "リファービッシュ", "refurbished", "再生品", "アウトレット",
    "キズ", "きず", "開封済み", "展示品",
    "整備済み", "renewed", "認定済み", "certified refurbished",
    # 非新品・品質問題
    "B級品", "B品", "返品", "デモ機", "モック",
    "サンプル品", "試供品", "動作未確認", "未検品",
    "欠品", "付属品欠品", "保証なし", "保証書なし",
    # 並行輸入・海外版（買取店が拒否することが多い）
    "並行輸入", "海外版", "海外モデル", "import",
    # 非正規品
    "非正規品", "非純正", "コピー品", "模倣品", "ノーブランド",
]

_EXCLUDED_KEYWORDS = [
    "まごころ長期修理保証", "長期修理保証", "延長保証", "保証プラン",
    "レンタル", "rental", "貸出", "リース",
    "店頭のみ", "店頭販売", "店頭受取", "店舗限定", "店頭限定",
    # 納期・入手リスク
    "取り寄せ", "お取り寄せ", "予約", "受注生産",
    # 非物理商品
    "ダウンロード版", "DL版",
    # 転売不可・特殊販売形態
    "ふるさと納税", "クーポン", "ギフト券", "商品券",
    "法人向け", "業務用", "セット販売のみ",
]

# アクセサリ・関連商品を示すキーワード（本体検索時にヒットする周辺商品を弾く）
_ACCESSORY_KEYWORDS = [
    "ケース", "カバー", "フィルム", "保護", "シール", "スキン",
    "ストラップ", "スタンド", "ホルダー", "マウント", "アダプタ",
    "アダプター", "充電器", "充電ケーブル", "ケーブル",
    "リモコン", "交換用", "替え", "替刃", "フィルター",
    "インク", "トナー", "用紙", "対応", "専用",
    "互換", "汎用", "サードパーティ", "社外品",
    # 部品・パーツ系
    "バッテリー", "電池", "パーツ", "部品", "付属品",
    "カートリッジ", "ノズル", "ブラシ", "ヘッド",
    "パッド", "ローラー", "紙パック", "ダストカップ",
    "ベルト", "パッキン",
    "蓋", "キャップ", "ドック", "クレードル",
    "タッチペン", "スタイラスペン",
    # 釣具・スポーツ用品系パーツ
    "スプール", "ハンドルノブ", "ベアリング", "ドラグワッシャー",
    # トレカ・バラ売り系
    "シングルカード", "シングル", "バラ売り", "バラ",
    "1枚", "プロモ", "プロモーション",
    # 消耗品・詰替
    "リフィル", "詰め替え", "詰替",
    # 修理・メンテナンス
    "修理", "リペア", "メンテナンス",
    # 収納・持ち運び
    "ポーチ", "収納袋", "キャリングケース",
    # 接続・延長・変換
    "延長コード", "変換", "コネクタ",
    # 楽器パーツ
    "マウスピース", "リード", "弦", "ピック",
    # カードゲーム周辺
    "スリーブ", "デッキケース", "プレイマット",
    # グリップ・先端
    "グリップ", "チップ", "先端",
    # 取付工事系（工事費込で価格膨張）
    "設置込み", "工事費込み", "取付工事",
    # カメラ関連アクセサリ
    "レンズキャップ", "ボディキャップ", "レンズフード", "レンズペン",
    "液晶保護", "スクリーンプロテクター", "アイカップ", "アイピース",
    "リモートコード", "レリーズ", "グリップベルト",
    "カメラバッグ", "カメラポーチ", "ショルダーストラップ",
    # ゲーム関連アクセサリ
    "コントローラー", "コントローラ", "ヘッドセット", "充電スタンド",
]


def _is_used_item(name: str) -> bool:
    """商品名から中古品かどうかを判定する"""
    name_lower = name.lower()
    return any(kw in name_lower for kw in _USED_KEYWORDS)


def _is_excluded_item(name: str) -> bool:
    """除外対象の非商品（保証サービス等）かどうかを判定する"""
    return any(kw in name for kw in _EXCLUDED_KEYWORDS)


def _extract_specs(name: str) -> set[str]:
    """商品名から数値スペック（型番・サイズ・F値等）を抽出する"""
    return set(_re.findall(r"\d+(?:[.\-/]\d+)*(?:mm|gb|tb|mhz|inch|インチ)?", name.lower()))


def _is_likely_accessory(csv_name: str, ec_name: str) -> bool:
    """EC商品名がCSV商品（本体）のアクセサリっぽいかを判定する

    CSV商品名にアクセサリキーワードが含まれない場合のみ判定する。
    （CSV側がアクセサリ商品なら本体がヒットしても問題ないため）
    """
    if not csv_name or not ec_name:
        return False

    csv_lower = csv_name.lower()
    ec_lower = ec_name.lower()

    # CSV商品名自体にアクセサリキーワードがあればスキップ（アクセサリを探している）
    csv_has_accessory = any(kw in csv_lower for kw in _ACCESSORY_KEYWORDS)
    if csv_has_accessory:
        return False

    # EC商品名にアクセサリキーワードがあれば除外
    return any(kw in ec_lower for kw in _ACCESSORY_KEYWORDS)


_SCRAPER_SOURCES = {
    "Amazon", "ヨドバシ", "価格.com", "Qoo10",
    "ビックカメラ", "ジョーシン", "ノジマ", "ケーズデンキ",
    "ソフマップ", "エディオン", "コジマ",
}
_SUSPICIOUS_PRICE_RATIO = 0.25  # EC価格が買取価格の25%以下 → 除外
_HIGH_PROFIT_RATIO = 0.50  # EC価格が買取価格の50%以下 → 警告（利益が極端に高い）


def _is_suspicious_price_ratio(kaitori_price: int, ec_price: int) -> bool:
    """EC価格が買取価格に対して極端に安い場合、アクセサリ誤マッチの疑いあり（除外用）"""
    if kaitori_price <= 0 or ec_price <= 0:
        return False
    return ec_price / kaitori_price < _SUSPICIOUS_PRICE_RATIO


def _is_high_profit_ratio(kaitori_price: int, ec_price: int) -> bool:
    """利益が極端に高い場合、誤マッチの可能性あり（警告用）"""
    if kaitori_price <= 0 or ec_price <= 0:
        return False
    return ec_price / kaitori_price < _HIGH_PROFIT_RATIO


def _is_name_mismatch(csv_name: str, ec_name: str) -> bool:
    """買取商品名とEC商品名が明らかに異なるかを判定する

    1. アクセサリ判定
    2. 数値スペックの一致率で判定
    """
    if not csv_name or not ec_name:
        return False

    # アクセサリ判定
    if _is_likely_accessory(csv_name, ec_name):
        return True

    csv_specs = _extract_specs(csv_name)
    ec_specs = _extract_specs(ec_name)

    # どちらもスペックがなければ文字列類似度にフォールバック
    if not csv_specs and not ec_specs:
        ratio = difflib.SequenceMatcher(None, csv_name.lower(), ec_name.lower()).ratio()
        return ratio < 0.4

    # スペックがある場合: 一致率を計算
    if not csv_specs or not ec_specs:
        return False

    overlap = csv_specs & ec_specs
    total = csv_specs | ec_specs
    spec_ratio = len(overlap) / len(total) if total else 1.0

    return spec_ratio < 0.3


def search_rakuten_by_jan(jan_code: str) -> dict | None:
    """楽天でJAN検索し、最安値を返す"""
    if not RAKUTEN_APP_ID or not RAKUTEN_ACCESS_KEY:
        return None

    params = {
        "applicationId": RAKUTEN_APP_ID,
        "accessKey": RAKUTEN_ACCESS_KEY,
        "keyword": jan_code,
        "hits": 5,
        "sort": "+itemPrice",
        "availability": 1,
    }

    resp = _get_with_retry(RAKUTEN_SEARCH_URL, params, RAKUTEN_HEADERS)
    if not resp:
        return None

    data = resp.json()
    results = []
    for item in data.get("Items", []):
        item_data = item.get("Item", {})
        price = item_data.get("itemPrice", 0)
        name = item_data.get("itemName", "")

        # JAN検証: 商品URL・商品コード・商品名にJANが含まれるか確認
        item_url = item_data.get("itemUrl", "")
        item_code = item_data.get("itemCode", "")
        jan_found = (
            jan_code in item_url
            or jan_code in item_code
            or jan_code in name
        )
        if not jan_found:
            logger.debug("JAN不一致スキップ: 検索=%s 結果=%s", jan_code, name[:40])
            continue

        if price > 0 and not _is_used_item(name) and not _is_excluded_item(name):
            # postageFlag: 0=送料別, 1=送料込, 2=送料無料
            postage_flag = item_data.get("postageFlag", 0)
            free_shipping = postage_flag in (1, 2)
            entry = {
                "name": name,
                "price": price,
                "shop": item_data.get("shopName", ""),
                "url": item_data.get("itemUrl", ""),
                "points": int(price * RAKUTEN_POINT_RATE),
                "source": "楽天",
                "stock_status": "in_stock",
            }
            if free_shipping:
                entry["free_shipping"] = True
            results.append(entry)

    return min(results, key=lambda x: x["price"]) if results else None


def search_yahoo_by_jan(jan_code: str) -> dict | None:
    """YahooでJAN検索し、最安値を返す"""
    if not YAHOO_APP_ID:
        return None

    params = {
        "appid": YAHOO_APP_ID,
        "jan_code": jan_code,
        "results": 10,
        "sort": "+price",
        "in_stock": "true",
        "condition": "new",
    }

    resp = _get_with_retry(YAHOO_SEARCH_URL, params)
    if not resp:
        return None

    data = resp.json()
    results = []
    for item in data.get("hits", []):
        price = item.get("price", 0)
        item_name = item.get("name", "")
        if price > 0 and not _is_used_item(item_name) and not _is_excluded_item(item_name):
            point_info = item.get("point", {})
            bonus = point_info.get("lyLimitedBonusAmount", 0) or 0
            premium_bonus = point_info.get("premiumBonusAmount", 0) or 0
            base_point = int(price * 0.01)
            total_points = base_point + bonus + premium_bonus

            # shipping: "free"=送料無料, 数値=送料額
            shipping_info = item.get("shipping", {})
            free_shipping = shipping_info.get("code") == "free" if isinstance(shipping_info, dict) else str(shipping_info) == "free"
            entry = {
                "name": item.get("name", ""),
                "price": price,
                "shop": item.get("seller", {}).get("name", ""),
                "url": item.get("url", ""),
                "points": total_points,
                "source": "Yahoo",
                "stock_status": "in_stock",
            }
            if free_shipping:
                entry["free_shipping"] = True
            results.append(entry)

    return min(results, key=lambda x: x["price"]) if results else None


# APIレート制限用ロック（同一API内の連続呼び出し間隔を保証）
_rakuten_lock = threading.Lock()
_yahoo_lock = threading.Lock()
_last_rakuten_call = 0.0
_last_yahoo_call = 0.0
_API_INTERVAL = 1.0  # 秒（429時は_get_with_retryが自動リトライ）


def _rate_limited_rakuten(jan_code: str) -> dict | None:
    global _last_rakuten_call
    with _rakuten_lock:
        interval = _API_INTERVAL + random.uniform(0, 1.0)
        elapsed = time.time() - _last_rakuten_call
        if elapsed < interval:
            time.sleep(interval - elapsed)
        _last_rakuten_call = time.time()
    return search_rakuten_by_jan(jan_code)


def _rate_limited_yahoo(jan_code: str) -> dict | None:
    global _last_yahoo_call
    with _yahoo_lock:
        interval = _API_INTERVAL + random.uniform(0, 1.0)
        elapsed = time.time() - _last_yahoo_call
        if elapsed < interval:
            time.sleep(interval - elapsed)
        _last_yahoo_call = time.time()
    return search_yahoo_by_jan(jan_code)


def _verify_api_result(result: dict) -> dict | None:
    """API結果（楽天/Yahoo）の商品ページを訪問して検証する

    検証OKなら商品ページの実価格で更新した結果を返す。
    検証NG（除外条件該当・在庫切れ・価格乖離）なら None を返す。
    """
    url = result.get("url", "")
    if not url:
        return None

    from retailer_scraper import verify_ec_page

    verified = verify_ec_page(url, result.get("price", 0))
    if not verified:
        logger.info("API検証失敗（ページ取得不可）: %s %s", result.get("source"), url[:60])
        return None

    # 除外条件に該当
    if verified.get("excluded"):
        logger.info("API検証: 除外 (%s) %s", verified.get("reason"), result.get("name", "")[:40])
        return None

    # 在庫切れ
    if verified.get("stock_status") == "out_of_stock":
        logger.info("API検証: 在庫切れ %s", result.get("name", "")[:40])
        return None

    # 価格整合性チェック
    page_price = verified.get("price")
    if page_price and verified.get("price_consistent") is False:
        logger.info("API検証: 価格乖離 API=%s 実=%s %s",
                     result.get("price"), page_price, result.get("name", "")[:40])
        return None

    # 検証OKの場合、実ページの情報で結果を更新
    updated = dict(result)
    if page_price:
        updated["price"] = page_price
    if verified.get("stock_status") != "unknown":
        updated["stock_status"] = verified["stock_status"]
    if verified.get("name"):
        updated["name"] = verified["name"]
    if verified.get("points"):
        updated["points"] = verified["points"]
    if verified.get("url"):
        updated["url"] = verified["url"]
    updated["verified"] = True
    return updated


def search_best_ec_price(
    jan_code: str,
    include_retailers: bool = True,
    enabled_retailers: list | None = None,
    product_name: str = "",
    kaitori_price: int = 0,
    threshold: int = 0,
    shipping_cost: int = 0,
) -> dict | None:
    """全ECソースを並行検索し、最安値を返す

    楽天・Yahoo・スクレイパーを同時に実行して待ち時間を短縮。
    同一API内のレート制限はグローバルロックで保証。
    APIで利益が出る価格が見つかればスクレイパーをスキップ。
    """
    candidates = []
    results_lock = threading.Lock()
    api_done = threading.Event()
    api_profitable = threading.Event()

    def _search_and_collect(fn, *args):
        result = fn(*args)
        if result:
            with results_lock:
                candidates.append(result)
                # APIで利益確定ならフラグを立てる
                if kaitori_price > 0 and (kaitori_price - result["price"] - shipping_cost) >= threshold:
                    api_profitable.set()

    # 楽天・Yahoo を並行実行
    t_rakuten = threading.Thread(target=_search_and_collect, args=(_rate_limited_rakuten, jan_code))
    t_yahoo = threading.Thread(target=_search_and_collect, args=(_rate_limited_yahoo, jan_code))

    _THREAD_TIMEOUT = 30  # スレッドの最大待ち時間（秒）

    t_rakuten.start()
    t_yahoo.start()

    # スクレイパー: API と並行実行（APIで利益確定したらスキップ）
    t_retailers = None
    if include_retailers:
        from retailers import search_all_retailers

        def _search_retailers():
            # APIの完了を少し待つ（利益確定ならスキップ）
            api_profitable.wait(timeout=5)
            if api_profitable.is_set():
                return
            retailer_results = search_all_retailers(jan_code, enabled=enabled_retailers, product_name=product_name)
            with results_lock:
                candidates.extend(retailer_results)

        t_retailers = threading.Thread(target=_search_retailers, daemon=True)
        t_retailers.start()

    t_rakuten.join(timeout=_THREAD_TIMEOUT)
    t_yahoo.join(timeout=_THREAD_TIMEOUT)
    if t_retailers:
        t_retailers.join(timeout=_THREAD_TIMEOUT)

    # 商品名不一致フィルタ
    if product_name:
        candidates = [c for c in candidates if not _is_name_mismatch(product_name, c.get("name", ""))]

    if not candidates:
        return None

    # 価格比率フィルタ: 全ソース（API + スクレイパー）に適用
    # ヨドバシ等のスクレイパーも商品名検索のため、アクセサリが最安値でヒットする場合がある
    # 例: FUJIFILM X100VI(買取293,300円) → レンズフィルター(2,790円)
    if kaitori_price > 0:
        normal = [c for c in candidates if not _is_suspicious_price_ratio(kaitori_price, c["price"])]

        if normal:
            candidates = normal
        else:
            # 全て疑わしい → 最も高い（=本体に近い）結果を警告付きで返す
            best = max(candidates, key=lambda x: x["price"])
            best["price_warning"] = True
            return best

    best = min(candidates, key=lambda x: x["price"])

    # API結果（楽天/Yahoo）は商品ページ検証が必要
    if best.get("source") not in _SCRAPER_SOURCES and best.get("url"):
        verified = _verify_api_result(best)
        if verified:
            best = verified
        else:
            # 検証失敗: 次に安いスクレイパー結果があればそちらを使用
            scraper_only = [c for c in candidates if c.get("source") in _SCRAPER_SOURCES]
            if scraper_only:
                best = min(scraper_only, key=lambda x: x["price"])
            else:
                # スクレイパー結果もない場合、警告付きで返す
                best["price_warning"] = True

    # 高利益警告: API結果のみ。スクレイパー結果は信頼する
    if kaitori_price > 0 and best.get("source") not in _SCRAPER_SOURCES:
        if _is_high_profit_ratio(kaitori_price, best["price"]):
            best["price_warning"] = True

    return best


def search_all_ec_prices(
    jan_code: str,
    include_retailers: bool = True,
    enabled_retailers: list | None = None,
    product_name: str = "",
) -> list:
    """全ECソースを並行検索し、全結果をリストで返す（比較用）"""
    results = []
    threads = []
    results_lock = threading.Lock()

    def _collect(fn, *args):
        result = fn(*args)
        if result:
            with results_lock:
                results.append(result)

    t_r = threading.Thread(target=_collect, args=(_rate_limited_rakuten, jan_code))
    t_y = threading.Thread(target=_collect, args=(_rate_limited_yahoo, jan_code))
    threads.extend([t_r, t_y])

    if include_retailers:
        from retailers import search_all_retailers

        def _search_retailers():
            r = search_all_retailers(jan_code, enabled=enabled_retailers, product_name=product_name)
            with results_lock:
                results.extend(r)

        threads.append(threading.Thread(target=_search_retailers))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if product_name:
        results = [r for r in results if not _is_name_mismatch(product_name, r.get("name", ""))]

    return sorted(results, key=lambda x: x["price"])


# --- バッチ検索（2並列 + キャッシュ） ---

# JAN単位のEC検索結果キャッシュ（利益なしの結果も保存、ファイル永続化）
import json as _json
from pathlib import Path as _Path

_LOCAL_DATA_DIR = _Path.home() / ".kaitori-viewer"
_LOCAL_DATA_DIR.mkdir(exist_ok=True)
_EC_CACHE_FILE = _LOCAL_DATA_DIR / "ec_cache.json"
_ec_cache: dict[str, dict | None] = {}
_ec_cache_lock = threading.Lock()
_EC_CACHE_SENTINEL = "__no_result__"
_ec_cache_loaded = False

_EC_CACHE_TTL = 24 * 3600  # 通常キャッシュの有効期限（24時間）
_EC_CACHE_TTL_WARNING = 3 * 3600  # 検証失敗（price_warning）結果の有効期限（3時間）


def _load_ec_cache():
    global _ec_cache, _ec_cache_loaded
    if _ec_cache_loaded:
        return
    if _EC_CACHE_FILE.exists():
        try:
            _ec_cache = _json.loads(_EC_CACHE_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            _ec_cache = {}
    _ec_cache_loaded = True


def _save_ec_cache():
    """ECキャッシュをアトミックにファイル保存する（スナップショットコピーでロック外I/O）"""
    with _ec_cache_lock:
        snapshot = dict(_ec_cache)
    try:
        tmp = _EC_CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(_json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_EC_CACHE_FILE)
    except OSError:
        pass


def clear_ec_cache():
    """ECキャッシュを完全にクリアする（メモリ + ファイル）"""
    global _ec_cache, _ec_cache_loaded, _ec_cache_dirty
    with _ec_cache_lock:
        _ec_cache = {}
        _ec_cache_loaded = True  # 空の状態をロード済みとして扱う
        _ec_cache_dirty = 0
        try:
            if _EC_CACHE_FILE.exists():
                _EC_CACHE_FILE.unlink()
        except OSError:
            pass


def _is_cache_expired(entry) -> bool:
    """キャッシュエントリのTTLを確認する"""
    if not isinstance(entry, dict):
        # センチネル値（検索結果なし）は通常TTLで判定
        return False  # センチネルは _get_ec_cache 側で別途処理
    ts = entry.get("_cached_at", 0)
    if ts <= 0:
        return True  # タイムスタンプなし → 旧形式、期限切れ扱い
    elapsed = time.time() - ts
    ttl = _EC_CACHE_TTL_WARNING if entry.get("price_warning") else _EC_CACHE_TTL
    return elapsed > ttl


def _get_ec_cache(jan: str):
    with _ec_cache_lock:
        _load_ec_cache()
        val = _ec_cache.get(jan)
        if val is None:
            return None  # キャッシュに存在しない
        # センチネル値（検索結果なし）のTTLチェック
        if val == _EC_CACHE_SENTINEL:
            # センチネルにはタイムスタンプがないため、常に有効として扱う
            # （結果なし = 再検索しても変わらない可能性が高い）
            return val
        if not isinstance(val, dict):
            return val
        # TTL期限切れチェック
        if _is_cache_expired(val):
            del _ec_cache[jan]
            return None
        # キャッシュ辞書への直接書き込みによる汚染を防ぐためコピーを返す
        copy = dict(val)
        copy.pop("_cached_at", None)  # 内部フィールドは返さない
        return copy


_ec_cache_dirty = 0


def _set_ec_cache(jan: str, result: dict | None):
    global _ec_cache_dirty
    should_flush = False
    with _ec_cache_lock:
        if result is not None:
            entry = dict(result)
            entry["_cached_at"] = time.time()
            _ec_cache[jan] = entry
        else:
            _ec_cache[jan] = _EC_CACHE_SENTINEL
        _ec_cache_dirty += 1
        if _ec_cache_dirty >= 50:
            _ec_cache_dirty = 0
            should_flush = True
    # ロック外で保存（_save_ec_cache内でスナップショット取得時にロック取得するため）
    if should_flush:
        _save_ec_cache()


def batch_search_ec_prices(
    jan_list: list[str],
    on_progress: callable = None,
    on_result: callable = None,
    product_names: dict[str, str] | None = None,
    kaitori_prices: dict[str, int] | None = None,
    threshold: int = 0,
    shipping_cost: int = 0,
    include_retailers: bool = True,
) -> dict[str, dict | None]:
    """複数JANを楽天・Yahoo並行パイプラインで検索する

    楽天とYahooは各APIごとに独立したレート制限ロックを持つため、
    異なるAPI間は完全に並行実行される。ThreadPoolExecutorにより
    バッチ境界の待ちを排除し、ワーカーが空いた瞬間に次のJANを開始する。

    Args:
        jan_list: JANコードのリスト
        on_progress: 進捗コールバック fn(completed, total)
        on_result: 1件完了コールバック fn(jan, ec_result_or_none)
        product_names: {jan_code: 商品名}
        kaitori_prices: {jan_code: 買取価格}（プリフィルタ用）
        threshold: 利益閾値
        shipping_cost: 送料合計
        include_retailers: スクレイパー(Amazon/ヨドバシ)を使うか

    Returns:
        {jan_code: best_ec_result or None}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    names = product_names or {}
    prices = kaitori_prices or {}
    total = len(jan_list)
    completed = [0]
    progress_lock = threading.Lock()
    batch_start_time = time.time()

    def _search_one(jan: str):
        # プリフィルタ: 買取価格が閾値+送料以下なら検索スキップ
        kaitori = prices.get(jan, 0)
        if kaitori > 0 and kaitori <= threshold + shipping_cost:
            return jan, None

        # EC結果キャッシュチェック
        cached = _get_ec_cache(jan)
        if cached is not None:
            if cached == _EC_CACHE_SENTINEL:
                return jan, None
            return jan, cached

        best = search_best_ec_price(
            jan,
            include_retailers=include_retailers,
            product_name=names.get(jan, ""),
            kaitori_price=kaitori,
            threshold=threshold,
            shipping_cost=shipping_cost,
        )
        _set_ec_cache(jan, best)
        return jan, best

    def _worker(jan: str):
        jan_code, best = _search_one(jan)
        with progress_lock:
            results[jan_code] = best
            completed[0] += 1
            # ETA計算（10件ごとに表示）
            eta_str = ""
            if completed[0] % 10 == 0 or completed[0] == total:
                elapsed = time.time() - batch_start_time
                if completed[0] > 0 and completed[0] < total:
                    remaining = int(elapsed / completed[0] * (total - completed[0]))
                    eta_str = f" (残り約{remaining // 60}分{remaining % 60}秒)"
            if best:
                logger.info("[%d/%d] %s -> %s %s円%s", completed[0], total, jan_code, best["source"], f"{best['price']:,}", eta_str)
            else:
                logger.info("[%d/%d] %s -> EC結果なし%s", completed[0], total, jan_code, eta_str)
            if on_progress:
                on_progress(completed[0], total)

    # 楽天・Yahoo並行実行（ThreadPoolExecutor + レート制限ロックが各API間隔を保証）
    # 各JAN内で楽天・Yahooスレッドが並行起動、異なるJAN間もワーカー空き次第即開始
    # WORKERS=4: API層は rate-limited ロックで頭打ち、スクレイパー層は各ワーカーが独立
    #           ただしメモリ不足(WinError 1455)時は2に戻す
    WORKERS = 4
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        future_to_jan = {executor.submit(_worker, j): j for j in jan_list}
        for future in as_completed(future_to_jan):
            jan = future_to_jan[future]
            try:
                future.result()
            except Exception as e:
                logger.warning("検索エラー JAN %s: %s", jan, e)
            if on_result and jan in results:
                on_result(jan, results[jan])

    _save_ec_cache()
    return results
