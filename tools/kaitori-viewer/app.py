"""買取価格ビューア（表示・ソート・フィルタリング専用）"""

import html as _html
import json
import re as _re
from datetime import datetime as _dt
from pathlib import Path

import pandas as pd
import streamlit as st

from csv_loader import SHOP_NAMES, get_categories, is_excluded, load_csv

st.set_page_config(page_title="買取価格ビューア", layout="wide")

# --- キャッシュ読み込み（読み取り専用） ---
_LOCAL_DATA_DIR = Path.home() / ".kaitori-viewer"
_CACHE_FILE = _LOCAL_DATA_DIR / "cache_results.json"


def _load_cache() -> list:
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


ec_results = _load_cache()

# --- CSV読み込み ---
CSV_DIR = Path(__file__).resolve().parent.parent.parent


@st.cache(allow_output_mutation=True, show_spinner=True, suppress_st_warning=True)
def load_data(filepath: str) -> pd.DataFrame:
    return load_csv(filepath)


@st.cache(show_spinner=False, suppress_st_warning=True)
def cached_categories(filepath: str) -> list:
    return get_categories(load_data(filepath))


csv_files = sorted(CSV_DIR.glob("all_data_*.csv"), reverse=True)
if not csv_files:
    st.error("CSVファイルが見つかりません。amcompany/ に all_data_*.csv を配置してください。")
    st.stop()

# =====================================================================
# サイドバー
# =====================================================================

selected_csv = st.sidebar.selectbox("CSVファイル", csv_files, format_func=lambda p: p.name)

df = load_data(str(selected_csv)).copy()
if df.empty:
    st.error("CSVに有効なデータがありません。")
    st.stop()

# CSV鮮度
_ts_match = _re.search(r"all_data_(\d{12})", selected_csv.name)
if _ts_match:
    _csv_dt = _dt.strptime(_ts_match.group(1), "%Y%m%d%H%M")
    _age_days = (_dt.now() - _csv_dt).days
    st.sidebar.write(f"**データ**: {_csv_dt.strftime('%Y/%m/%d %H:%M')}  ({len(df):,}件)")
    if _age_days >= 3:
        st.sidebar.warning(f"データが{_age_days}日前です")

# 買取店
st.sidebar.header("買取店")
if "selected_shops" not in st.session_state:
    st.session_state.selected_shops = list(SHOP_NAMES)
selected_shops = st.sidebar.multiselect(
    "利用する買取店", SHOP_NAMES,
    default=st.session_state.selected_shops, key="shop_selector",
)
st.session_state.selected_shops = selected_shops

if set(selected_shops) != set(SHOP_NAMES):
    shop_price_cols = [f"{s}_価格" for s in selected_shops]
    available_price_cols = [c for c in shop_price_cols if c in df.columns]
    if available_price_cols:
        df["最高買取価格"] = df[available_price_cols].max(axis=1)

        def _best_shop(row):
            best_p, best_s = 0, ""
            for s in selected_shops:
                col = f"{s}_価格"
                if col in row.index and row[col] > best_p:
                    best_p = row[col]
                    best_s = s
            return best_s

        df["最高値店舗"] = df.apply(_best_shop, axis=1)
        df["買取店数"] = df[available_price_cols].apply(lambda r: (r > 0).sum(), axis=1)
        df = df[df["最高買取価格"] > 0]
    else:
        st.sidebar.warning("買取店を1つ以上選択してください")
        st.stop()

# フィルタ
st.sidebar.header("フィルタ")
keyword = st.sidebar.text_input("キーワード検索")
categories = cached_categories(str(selected_csv))
selected_cats = st.sidebar.multiselect("カテゴリ", categories)

min_price = int(df["最高買取価格"].min())
max_price = max(int(df["最高買取価格"].max()), min_price + 1000)
price_range = st.sidebar.slider(
    "買取価格帯", min_value=min_price, max_value=max_price,
    value=(min_price, max_price), step=1000,
)

exclude_enabled = st.sidebar.checkbox("除外フィルタ（iPhone・中古・破損等）", value=True)

# フィルタ適用
filtered = df.copy()
if keyword:
    mask = filtered["商品名"].str.contains(keyword, case=False, na=False) | filtered["JAN"].str.contains(keyword, na=False)
    filtered = filtered[mask]
if selected_cats:
    filtered = filtered[filtered["カテゴリ"].apply(lambda x: any(cat in str(x) for cat in selected_cats))]
filtered = filtered[(filtered["最高買取価格"] >= price_range[0]) & (filtered["最高買取価格"] <= price_range[1])]
if exclude_enabled:
    filtered = filtered[~filtered.apply(lambda r: is_excluded(r["商品名"], r.get("カテゴリ", "")), axis=1)]

st.sidebar.write(f"**フィルタ後**: {len(filtered):,}")

# =====================================================================
# 共通ユーティリティ
# =====================================================================

PROFIT_DISPLAY_COLS = [
    "JAN", "商品名", "最高買取価格", "買取店", "買取確認",
    "EC最安値", "ECソース", "送料", "現金利益", "ROI(%)",
    "在庫状況", "ポイント", "PT込利益", "商品リンク", "取得日時",
]


def _safe_link(url: str, label: str) -> str:
    """URLをサニタイズしてリンクHTMLを生成する"""
    if not url:
        return ""
    url = str(url).strip()
    if not url.startswith(("https://", "http://")):
        return ""
    escaped = _html.escape(url, quote=True)
    return f'<a href="{escaped}" target="_blank" rel="noopener noreferrer">{label}</a>'


def _render_profit_table(container, dataframe):
    """リンク列をクリック可能なHTMLテーブルとして描画"""
    render_df = dataframe.copy()
    if "商品リンク" in render_df.columns:
        render_df["商品リンク"] = render_df["商品リンク"].apply(
            lambda u: _safe_link(u, "リンク")
        )
    if "買取確認" in render_df.columns:
        render_df["買取確認"] = render_df["買取確認"].apply(
            lambda u: _safe_link(u, "確認")
        )
    table_html = render_df.to_html(escape=False, index=False)
    container.write(table_html, unsafe_allow_html=True)


# =====================================================================
# メインエリア
# =====================================================================

st.title("買取価格ビューア")

# -------------------------------------------------------------------
# セクション1: 利益一覧テーブル
# -------------------------------------------------------------------

st.header("利益一覧")

if ec_results:
    result_df = pd.DataFrame(ec_results)

    # フィルタ・ソート
    min_profit_filter = st.slider(
        "最低利益フィルタ(円)", min_value=-10000, max_value=50000,
        value=3000, step=500, key="min_profit",
    )

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        hide_oos = st.checkbox("在庫なしを除外", value=False, key="hide_oos",
                               help="OFFにすると入荷待ち商品も表示（再入荷時に即購入用）")
    with col_f2:
        hide_warnings = st.checkbox("要確認（価格差大）を除外", value=True, key="hide_warnings")

    if hide_oos and "stock_status" in result_df.columns:
        result_df = result_df[result_df["stock_status"] != "out_of_stock"]
    if hide_warnings and "price_warning" in result_df.columns:
        result_df = result_df[result_df["price_warning"] != True]
    if "現金利益" in result_df.columns:
        result_df = result_df[result_df["現金利益"] >= min_profit_filter].sort_values("PT込利益", ascending=False)

    # メトリクス
    m1, m2, m3 = st.columns(3)
    m1.metric("総件数", f"{len(ec_results)}件")
    m2.metric("表示中", f"{len(result_df)}件")
    if len(result_df) > 0 and "PT込利益" in result_df.columns:
        m3.metric("最大PT込利益", f"{int(result_df['PT込利益'].max()):,}円")

    # テーブル
    if "在庫状況" not in result_df.columns:
        result_df["在庫状況"] = "未確認"
    available = [c for c in PROFIT_DISPLAY_COLS if c in result_df.columns]
    table_area = st.empty()
    _render_profit_table(table_area, result_df[available])

    st.caption("※ 現金利益 = 最高買取価格 - EC最安値 - 送料 ／ PT込利益 = 現金利益 + ポイント")

    # CSVダウンロード
    csv_data = result_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("利益一覧CSVダウンロード", csv_data, "profit_results.csv", "text/csv")
else:
    st.info("利益商品がありません。`python auto_extract.py` でEC検索を実行してください。")

# -------------------------------------------------------------------
# セクション2: 買取価格一覧
# -------------------------------------------------------------------

with st.expander("買取価格一覧（CSV全データ）"):
    col_a, col_b = st.columns(2)
    with col_a:
        sort_col = st.selectbox("ソート", ["利益候補スコア", "最高買取価格", "買取店数", "商品名"], index=0)
    with col_b:
        sort_asc = st.checkbox("昇順", value=False)

    display_df = filtered.sort_values(sort_col, ascending=sort_asc).reset_index(drop=True)
    # 買取店間価格差を追加
    display_df["価格差"] = display_df["最高買取価格"] - display_df["2番目価格"]
    list_cols = ["JAN", "商品名", "最高買取価格", "最高値店舗", "価格差", "カテゴリ", "買取店数", "2番目価格", "利益候補スコア"]
    st.dataframe(display_df[list_cols], height=400)

    show_shops = st.checkbox("店舗別価格を表示")
    if show_shops:
        shop_cols = ["JAN", "商品名"] + [f"{name}_価格" for name in SHOP_NAMES]
        shop_df = display_df[shop_cols].copy()
        for name in SHOP_NAMES:
            price_col = f"{name}_価格"
            shop_df[price_col] = shop_df[price_col].apply(lambda x: f"{x:,}円" if x > 0 else "-")
        st.dataframe(shop_df, height=400)

    csv_export = display_df[list_cols].to_csv(index=False).encode("utf-8-sig")
    st.download_button("買取一覧CSVダウンロード", csv_export, "kaitori_filtered.csv", "text/csv")
