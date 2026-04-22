"""買取価格CSVの読み込みと正規化"""

import json
from pathlib import Path

import pandas as pd

# 過去利益実績（cache_results.json）の履歴ボーナス
_PROFITABLE_JANS_CACHE: set[str] | None = None


def _load_profitable_jans() -> set[str]:
    """過去に利益が出たJANをcache_results.jsonから読み込む（1回のみ）"""
    global _PROFITABLE_JANS_CACHE
    if _PROFITABLE_JANS_CACHE is not None:
        return _PROFITABLE_JANS_CACHE

    cache_file = Path.home() / ".kaitori-viewer" / "cache_results.json"
    jans: set[str] = set()
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            for r in data:
                if r.get("現金利益", 0) > 0 and r.get("JAN"):
                    jans.add(str(r["JAN"]))
        except (json.JSONDecodeError, OSError):
            pass

    _PROFITABLE_JANS_CACHE = jans
    return jans


def _history_bonus(jan: str) -> float:
    """過去利益実績ボーナス（過去に利益が出たJANは1.5倍）"""
    return 1.5 if jan in _load_profitable_jans() else 1.0

SHOP_CONFIGS = [
    {"prefix": "アバウテック", "name_col": 1, "price_col": 2, "date_col": 3, "cat_col": 4,
     "search_url": "https://www.aboutec.jp/purchase/?keywords={JAN}"},
    {"prefix": "けんさく", "name_col": 5, "price_col": 6, "date_col": 7, "cat_col": 8,
     "search_url": ""},
    {"prefix": "商店", "name_col": 9, "price_col": 10, "date_col": 11, "cat_col": 12,
     "search_url": "https://www.kaitorishouten-co.jp/?s={JAN}"},
    {"prefix": "森森", "name_col": 13, "price_col": 14, "date_col": 15, "cat_col": 16,
     "search_url": ""},
    # col 20 = 一丁目_リンク（CSV内にURL直接保存）, col 21 = メインカテゴリ
    {"prefix": "一丁目", "name_col": 17, "price_col": 18, "date_col": 19, "cat_col": 21,
     "link_col": 20, "search_url": ""},
    {"prefix": "ウィキ", "name_col": 22, "price_col": 23, "date_col": 24, "cat_col": 25,
     "search_url": ""},
    {"prefix": "家電市場", "name_col": 26, "price_col": 27, "date_col": 28, "cat_col": 29,
     "search_url": ""},
    {"prefix": "モバイル一番", "name_col": 30, "price_col": 31, "date_col": 32, "cat_col": 33,
     "search_url": ""},
    {"prefix": "ルデヤ", "name_col": 34, "price_col": 35, "date_col": 36, "cat_col": 37,
     "search_url": "https://kaitori-rudeya.com/?s={JAN}"},
    {"prefix": "ホムラ", "name_col": 38, "price_col": 39, "date_col": 40,
     "search_url": ""},
    {"prefix": "モバミ", "name_col": 41, "price_col": 42, "date_col": 43,
     "search_url": ""},
]

# 店舗名 → 検索URLテンプレートの辞書
SHOP_SEARCH_URLS = {s["prefix"]: s.get("search_url", "") for s in SHOP_CONFIGS}

SHOP_NAMES = [s["prefix"] for s in SHOP_CONFIGS]

# 除外フィルタ
EXCLUDED_PRODUCTS = ["iPhone", "アイフォン", "iPad", "アイパッド"]
# 状態不良（真の除外対象）
_BAD_CONDITIONS = [
    "汚れ", "破損", "ジャンク", "訳あり", "難あり", "故障", "欠品", "傷あり", "中古",
]
# 生産終了マーカー（戦略T: 除外ではなく希少化シグナルとして扱う）
_DISCONTINUED_MARKERS = [
    "販売終了", "販売中止", "販売休止", "生産終了", "廃番", "生産完了",
]
# 後方互換性のため旧定数を残す（is_excluded では BAD のみ使用）
EXCLUDED_CONDITIONS = _BAD_CONDITIONS + _DISCONTINUED_MARKERS

# 大型商品キーワード（送料高額・返品困難・倉庫スペース必要なため仕入対象外）
# 誤検出回避のため、部分一致しやすい短いキーワード（「机」「デスク」「棚」等）は
# 具体的な複合語のみを採用する（「デスクトップパソコン」を誤って除外しないため）
_OVERSIZED_KEYWORDS = [
    # 大型家電
    "冷蔵庫", "冷凍庫", "洗濯機", "衣類乾燥機", "洗濯乾燥機",
    "食洗機", "食器洗い機", "食器乾燥機",
    "エアコン", "業務用エアコン", "ルームエアコン",
    "加湿空気清浄機",  # 「空気清浄機」単独は小型あり除外せず
    # 大型キッチン家電
    "オーブンレンジ", "ビルトイン", "システムキッチン", "ガスレンジ",
    "IHクッキングヒーター", "業務用",
    # 大型テレビ（インチ数で判定、50型以上）
    "50インチ", "50型", "55インチ", "55型", "60インチ", "60型",
    "65インチ", "65型", "70インチ", "70型", "75インチ", "75型",
    "80インチ", "80型", "85インチ", "85型", "100インチ", "100型",
    "110インチ", "110型", "大型テレビ",
    # 家具（具体的な複合語のみ、単独「机」「デスク」「棚」「ベッド」は誤検出回避）
    "ソファー", "ソファベッド",
    "ダブルベッド", "シングルベッド", "セミダブルベッド", "クイーンベッド",
    "マットレス",
    "学習机", "オフィスデスク", "作業机", "事務デスク",
    "食器棚", "本棚", "タンス", "洋服タンス", "チェスト",
    "ダイニングテーブル", "ダイニングセット",
    # 楽器（大型）
    "グランドピアノ", "アップライトピアノ", "電子ピアノ",
    "ドラムセット", "電子ドラム",
    # アウトドア・車両
    "自転車", "電動自転車", "原付", "オートバイ", "スクーター",
    "芝刈り機", "除雪機", "雪かき機",
    "発電機", "船外機", "耕運機", "耕うん機",
    "自動車", "モペット",
    # その他大型
    "マッサージチェア", "リクライニングチェア",
    "給湯器", "エコキュート", "ガス給湯器",
    "サウナ", "バスタブ",
    "大型金庫",
    "コピー機", "複合機", "業務用プリンター",
    "自動販売機",
    # 店舗設備
    "ショーケース", "陳列棚", "レジスター",
]


CARD_GAME_CATEGORIES = ["トレーディングカード"]
CARD_GAME_BOX_KEYWORDS = ["ボックス", "BOX", "box", "Box"]


def is_oversized(product_name: str, category: str = "") -> bool:
    """大型商品（送料高額・返品困難）かどうかを判定する"""
    if not product_name and not category:
        return False
    haystack = f"{product_name} {category}"
    return any(kw in haystack for kw in _OVERSIZED_KEYWORDS)


def is_excluded(product_name: str, category: str = "", exclude_oversized: bool = True) -> bool:
    """商品名が除外対象かどうかを判定する。

    Args:
        product_name: 商品名
        category: カテゴリ名
        exclude_oversized: 大型商品も除外するか（デフォルト True、仕入対象外）
    """
    name_lower = product_name.lower()
    for word in EXCLUDED_PRODUCTS:
        if word.lower() in name_lower:
            return True
    for word in _BAD_CONDITIONS:
        if word in product_name:
            return True
    # カードゲームはボックス以外を除外
    if any(cat in category for cat in CARD_GAME_CATEGORIES):
        if not any(kw.lower() in name_lower for kw in CARD_GAME_BOX_KEYWORDS):
            return True
    # 大型商品除外（送料・倉庫・返品リスクのため）
    if exclude_oversized and is_oversized(product_name, category):
        return True
    return False


def is_discontinued(product_name: str) -> bool:
    """生産終了・販売終了マーカーを含むか（戦略T: 希少化シグナル）"""
    if not product_name:
        return False
    return any(m in product_name for m in _DISCONTINUED_MARKERS)


def load_csv(filepath: str) -> pd.DataFrame:
    """買取価格CSVを読み込み、正規化されたDataFrameを返す"""
    df = pd.read_csv(filepath, encoding="cp932", dtype=str, on_bad_lines="skip")
    header = list(df.columns)

    num_cols = len(df.columns)
    records = []
    for row in df.itertuples(index=False):
        jan = str(row[0]).strip() if pd.notna(row[0]) else ""
        if not jan:
            continue

        best_price = 0
        best_shop = ""
        best_name = ""
        best_link = ""
        categories = set()
        shop_prices = {}

        for shop in SHOP_CONFIGS:
            price_val = row[shop["price_col"]] if shop["price_col"] < num_cols else "0"
            name_val = row[shop["name_col"]] if shop["name_col"] < num_cols else ""

            try:
                price_str = str(price_val).strip().replace(",", "") if pd.notna(price_val) else ""
                price = int(price_str) if price_str else 0
            except (ValueError, TypeError):
                price = 0

            if price <= 0:
                continue

            name = str(name_val).strip() if pd.notna(name_val) else ""
            # 店舗固有リンク（一丁目等）
            link = ""
            link_col = shop.get("link_col")
            if link_col and link_col < num_cols:
                link_val = row[link_col]
                if pd.notna(link_val) and str(link_val).strip():
                    link = str(link_val).strip()

            shop_prices[shop["prefix"]] = {"price": price, "name": name, "link": link}

            if price > best_price:
                best_price = price
                best_shop = shop["prefix"]
                best_name = name
                best_link = link

            cat_col = shop.get("cat_col")
            if cat_col and cat_col < num_cols:
                cat_val = row[cat_col]
                if pd.notna(cat_val) and str(cat_val).strip():
                    categories.add(str(cat_val).strip())

        if best_price <= 0:
            continue

        product_name = best_name
        if not product_name:
            for sp in shop_prices.values():
                if sp["name"]:
                    product_name = sp["name"]
                    break

        # 利益候補スコア算出（戦略A+D: 買取店間価格差 + 履歴ボーナス）
        all_prices = sorted(
            [sp["price"] for sp in shop_prices.values()],
            reverse=True,
        )
        second_price = all_prices[1] if len(all_prices) >= 2 else 0
        price_gap = best_price - second_price
        shop_count = len(shop_prices)

        # === 外れ値検出: 最高値が 2位/中央値から極端に乖離していないか ===
        # 家電市場のように1店舗だけ高い提示で実際は買取されないケース対策。
        # 信頼買取価格 (reliable_price) は保守的な見積で、実際の利益判定に使える。
        # - 最高値が2位の1.18倍超 かつ 3店舗以上ある場合は外れ値疑い
        # - そのときは 2位価格を信頼価格として採用
        is_outlier_best = False
        reliable_price = best_price
        if shop_count >= 3 and second_price > 0:
            outlier_ratio = best_price / second_price
            if outlier_ratio >= 1.18:
                is_outlier_best = True
                reliable_price = second_price

        # 戦略D: 買取店間価格差を「プラス評価」に反転
        # 1店舗だけ突出 = 情報の非対称性 = 狙い目
        gap_score = price_gap * shop_count if shop_count >= 2 else shop_count

        # 戦略A: 過去利益実績ボーナス
        bonus = _history_bonus(jan)

        # 新スコア = 買取価格 × gap_score × ボーナス / 1000
        # gap_score=0 時は買取価格×店舗数だけでもスコアが出るようにフォールバック
        if gap_score > 0:
            profit_score = round(best_price * gap_score * bonus / 1000)
        else:
            profit_score = round(best_price * shop_count * bonus / 1000)

        # 買取確認リンク: CSV内リンク > 検索URLテンプレート
        kaitori_url = best_link
        if not kaitori_url:
            search_tmpl = SHOP_SEARCH_URLS.get(best_shop, "")
            if search_tmpl:
                kaitori_url = search_tmpl.replace("{JAN}", jan)

        # 戦略T: 商品名または各店舗の商品名のいずれかに生産終了マーカーがあれば True
        discontinued = is_discontinued(product_name) or any(
            is_discontinued(sp.get("name", "")) for sp in shop_prices.values()
        )

        records.append({
            "JAN": jan,
            "商品名": product_name,
            "最高買取価格": best_price,
            "最高値店舗": best_shop,
            "買取確認": kaitori_url,
            "カテゴリ": "、".join(sorted(categories)) if categories else "",
            "買取店数": shop_count,
            "2番目価格": second_price,
            "信頼買取価格": reliable_price,  # 外れ値を補正した保守的価格
            "最高値_外れ値": is_outlier_best,
            "利益候補スコア": profit_score,
            "生産終了": discontinued,
            **{f"{name}_価格": shop_prices.get(name, {}).get("price", 0) for name in SHOP_NAMES},
        })

    result = pd.DataFrame(records)
    result = result.sort_values("最高買取価格", ascending=False).reset_index(drop=True)
    return result


def get_categories(df: pd.DataFrame) -> list[str]:
    """ユニークなカテゴリ一覧を返す"""
    all_cats = set()
    for cats in df["カテゴリ"].dropna():
        for cat in str(cats).split("、"):
            cat = cat.strip()
            if cat:
                all_cats.add(cat)
    return sorted(all_cats)
