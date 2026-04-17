"""買取価格CSVの読み込みと正規化"""

import pandas as pd

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
EXCLUDED_CONDITIONS = [
    "汚れ", "破損", "ジャンク", "訳あり", "難あり", "故障", "欠品", "傷あり", "中古",
    "販売終了", "販売中止", "販売休止", "生産終了", "廃番", "生産完了",
]


CARD_GAME_CATEGORIES = ["トレーディングカード"]
CARD_GAME_BOX_KEYWORDS = ["ボックス", "BOX", "box", "Box"]


def is_excluded(product_name: str, category: str = "") -> bool:
    """商品名が除外対象かどうかを判定する"""
    name_lower = product_name.lower()
    for word in EXCLUDED_PRODUCTS:
        if word.lower() in name_lower:
            return True
    for word in EXCLUDED_CONDITIONS:
        if word in product_name:
            return True
    # カードゲームはボックス以外を除外
    if any(cat in category for cat in CARD_GAME_CATEGORIES):
        if not any(kw.lower() in name_lower for kw in CARD_GAME_BOX_KEYWORDS):
            return True
    return False


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

        # 利益候補スコア算出
        all_prices = sorted(
            [sp["price"] for sp in shop_prices.values()],
            reverse=True,
        )
        second_price = all_prices[1] if len(all_prices) >= 2 else 0
        price_gap = best_price - second_price  # 最高値と2番目の差
        shop_count = len(shop_prices)
        # スコア = 買取価格 × 買取店数 ÷ (価格差 + 1)
        profit_score = round(best_price * shop_count / (price_gap + 1))

        # 買取確認リンク: CSV内リンク > 検索URLテンプレート
        kaitori_url = best_link
        if not kaitori_url:
            search_tmpl = SHOP_SEARCH_URLS.get(best_shop, "")
            if search_tmpl:
                kaitori_url = search_tmpl.replace("{JAN}", jan)

        records.append({
            "JAN": jan,
            "商品名": product_name,
            "最高買取価格": best_price,
            "最高値店舗": best_shop,
            "買取確認": kaitori_url,
            "カテゴリ": "、".join(sorted(categories)) if categories else "",
            "買取店数": shop_count,
            "2番目価格": second_price,
            "利益候補スコア": profit_score,
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
