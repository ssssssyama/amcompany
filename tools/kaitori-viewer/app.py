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

# 最高買取価格列で「最高 / 信頼」を2段表示、現金利益列で「現金 / 上振れ時」を2段表示する。
# そのため信頼買取価格・上振れ時利益の独立列は持たない（重複表示防止）。
PROFIT_DISPLAY_COLS = [
    "JAN", "外れ値", "プレミア", "経路", "商品名", "最高買取価格", "上振れ余地",
    "買取店", "買取確認",
    "EC最安値", "ECソース", "送料",
    "現金利益", "ROI(%)",
    "在庫状況", "ポイント", "PT込利益", "商品リンク", "取得日時",
]

# origin → 表示ラベル（アイコン + 文字）
ORIGIN_LABELS = {
    "chrome_extension": "🧩拡張",
    "api": "🛰️API",
    "scraper": "🕷️Scraper",
    "": "？",
    None: "？",
}


def _safe_link(url: str, label: str) -> str:
    """URLをサニタイズしてリンクHTMLを生成する"""
    if not url:
        return ""
    url = str(url).strip()
    if not url.startswith(("https://", "http://")):
        return ""
    escaped = _html.escape(url, quote=True)
    return f'<a href="{escaped}" target="_blank" rel="noopener noreferrer">{label}</a>'


def _format_profit_cell(row, col_profit="現金利益", col_upside="上振れ時利益",
                         col_upside_bonus="上振れ余地") -> str:
    """現金利益と上振れ時利益を2段表示するHTMLセルを返す"""
    profit = int(row.get(col_profit, 0) or 0)
    upside_profit = int(row.get(col_upside, profit) or profit)
    upside_bonus = int(row.get(col_upside_bonus, 0) or 0)
    color = "#2e7d32" if profit > 0 else "#f44336"
    sign = "+" if profit > 0 else ""
    html = f'<span style="color:{color};font-weight:bold">{sign}{profit:,}円</span>'
    if upside_bonus > 0:
        html += f'<br><small style="color:#888">↑上振れ時 +{upside_profit:,}円</small>'
    return html


def _format_kaitori_cell(row) -> str:
    """最高買取と信頼買取を並記する"""
    max_k = int(row.get("最高買取価格", 0) or 0)
    reliable = int(row.get("信頼買取価格", max_k) or max_k)
    outlier = bool(row.get("最高値_外れ値", False))
    if reliable < max_k:
        return (
            f'<span>{max_k:,}円</span><br>'
            f'<small style="color:#888">信頼 {reliable:,}円</small>'
        )
    return f"{max_k:,}円"


def _outlier_marker(row) -> str:
    """外れ値フラグを ⚠ アイコンで表示"""
    return "⚠" if row.get("最高値_外れ値") else ""


def _origin_label(row) -> str:
    """取得経路を絵文字アイコン付きラベルで返す"""
    origin = row.get("origin")
    if origin in ORIGIN_LABELS:
        return ORIGIN_LABELS[origin]
    return str(origin)


def _premium_marker(row) -> str:
    """プレミア化（買取 > 定価）を 🔥 + 倍率で表示"""
    if not row.get("プレミア化"):
        return ""
    ratio = row.get("買取_定価比") or 0
    if not ratio:
        return "🔥"
    if ratio >= 1.5:
        return f"🔥🔥🔥 {ratio}x"
    if ratio >= 1.2:
        return f"🔥🔥 {ratio}x"
    return f"🔥 {ratio}x"


def _render_profit_table(container, dataframe, cols: list[str]):
    """リンク列・ハイブリッド列をクリック可能なHTMLテーブルとして描画

    Args:
        cols: 表示する列の順序。外れ値/最高買取価格/現金利益 はここで整形される。
    """
    render_df = dataframe.copy()

    # 1. 外れ値マーカー列を事前に追加（PROFIT_DISPLAY_COLS に "外れ値" が含まれる）
    if "最高値_外れ値" in render_df.columns:
        render_df["外れ値"] = render_df.apply(_outlier_marker, axis=1)
    elif "外れ値" not in render_df.columns:
        render_df["外れ値"] = ""

    # 1b. 取得経路列（Chrome拡張/API/Scraperを識別）
    if "origin" in render_df.columns:
        render_df["経路"] = render_df.apply(_origin_label, axis=1)
    elif "経路" not in render_df.columns:
        render_df["経路"] = "？"

    # 1c. プレミア化列（🔥＋倍率で目立たせる）
    if "プレミア化" in render_df.columns:
        render_df["プレミア"] = render_df.apply(_premium_marker, axis=1)
    elif "プレミア" not in render_df.columns:
        render_df["プレミア"] = ""

    # 2. 最高買取価格 → 2段 HTML セル (最高 + 信頼)
    if "最高買取価格" in render_df.columns:
        render_df["最高買取価格"] = render_df.apply(_format_kaitori_cell, axis=1)

    # 3. 現金利益 → 2段 HTML セル (現金 + 上振れ時)
    if "現金利益" in render_df.columns:
        render_df["現金利益"] = render_df.apply(_format_profit_cell, axis=1)

    # 4. 数値列を円表示に統一（0 と空は空欄にして視覚ノイズ減らす）
    for col in ("上振れ余地", "EC最安値", "送料", "ポイント", "PT込利益"):
        if col in render_df.columns:
            render_df[col] = render_df[col].apply(
                lambda v: f"{int(v):,}円"
                if pd.notna(v) and v != "" and int(v or 0) > 0 else ""
            )

    # 5. リンク列
    if "商品リンク" in render_df.columns:
        render_df["商品リンク"] = render_df["商品リンク"].apply(
            lambda u: _safe_link(u, "リンク")
        )
    if "買取確認" in render_df.columns:
        render_df["買取確認"] = render_df["買取確認"].apply(
            lambda u: _safe_link(u, "確認")
        )

    # 6. 列順序を固定（存在する列のみ）
    display_cols = [c for c in cols if c in render_df.columns]
    render_df = render_df[display_cols]

    # pandas の to_html は classes= を「dataframe + 指定クラス」として出力するが、
    # Streamlit は <style> ブロックを削除することがあるためインラインスタイルに切替。
    # 生のHTMLを自前で組み立てる（罫線付き）。
    def _cell(content: str) -> str:
        return (
            '<td style="padding:6px 10px;border:1px solid #999;'
            'vertical-align:top;white-space:nowrap;background:transparent;">'
            f'{content}</td>'
        )

    def _header(content: str) -> str:
        return (
            '<th style="padding:6px 10px;border:1px solid #999;'
            'background:transparent;font-weight:bold;text-align:left;'
            'white-space:nowrap;">'
            f'{content}</th>'
        )

    rows_html = []
    # ヘッダ
    header_html = "<tr>" + "".join(_header(str(c)) for c in display_cols) + "</tr>"
    rows_html.append(header_html)
    # ボディ
    for _, r in render_df.iterrows():
        cells = []
        for c in display_cols:
            val = r.get(c, "")
            if pd.isna(val):
                val = ""
            cells.append(_cell(str(val)))
        rows_html.append("<tr>" + "".join(cells) + "</tr>")

    table_html = (
        '<div style="overflow-x:auto;">'
        '<table style="border-collapse:collapse;border:1px solid #999;'
        'font-size:0.9em;width:100%;background:transparent;">'
        + "".join(rows_html)
        + "</table></div>"
    )
    container.markdown(table_html, unsafe_allow_html=True)


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

    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        hide_oos = st.checkbox("在庫なしを除外", value=False, key="hide_oos",
                               help="OFFにすると入荷待ち商品も表示（再入荷時に即購入用）")
    with col_f2:
        hide_warnings = st.checkbox("要確認（価格差大）を除外", value=True, key="hide_warnings")
    with col_f3:
        safe_only = st.checkbox("安全商品のみ（外れ値除外）", value=False, key="safe_only",
                                help="⚠最高値_外れ値 の商品を非表示。信頼価格で確実利益が出る商品だけ表示")
    with col_f4:
        premium_only = st.checkbox("🔥プレミアのみ（買取>定価）", value=False, key="premium_only",
                                   help="定価より買取価格が高い希少化商品のみ表示")

    # 取得経路フィルタ（API/Scraper/Chrome拡張 のどれを見るか）
    origin_options = ["全て", "🛰️API", "🕷️Scraper", "🧩拡張", "？(旧データ)"]
    origin_filter = st.radio(
        "取得経路", origin_options, index=0, horizontal=True, key="origin_filter",
        help="Chrome拡張経由で取得された価格だけ見たい場合は「🧩拡張」を選択",
    )

    if hide_oos and "stock_status" in result_df.columns:
        result_df = result_df[result_df["stock_status"] != "out_of_stock"]
    if hide_warnings and "price_warning" in result_df.columns:
        result_df = result_df[result_df["price_warning"] != True]
    if safe_only and "最高値_外れ値" in result_df.columns:
        result_df = result_df[result_df["最高値_外れ値"] != True]
    if premium_only and "プレミア化" in result_df.columns:
        result_df = result_df[result_df["プレミア化"] == True]
    if origin_filter != "全て" and "origin" in result_df.columns:
        target_map = {
            "🛰️API": "api",
            "🕷️Scraper": "scraper",
            "🧩拡張": "chrome_extension",
            "？(旧データ)": None,
        }
        target = target_map.get(origin_filter)
        if target is None:
            result_df = result_df[result_df["origin"].isna() | (result_df["origin"] == "")]
        else:
            result_df = result_df[result_df["origin"] == target]
    if "現金利益" in result_df.columns:
        result_df = result_df[result_df["現金利益"] >= min_profit_filter].sort_values("PT込利益", ascending=False)

    # メトリクス
    # 経路別件数（キャッシュ全体から集計、フィルタ前）
    all_df = pd.DataFrame(ec_results) if ec_results else pd.DataFrame()
    n_api = int((all_df.get("origin") == "api").sum()) if "origin" in all_df.columns else 0
    n_scr = int((all_df.get("origin") == "scraper").sum()) if "origin" in all_df.columns else 0
    n_ext = int((all_df.get("origin") == "chrome_extension").sum()) if "origin" in all_df.columns else 0
    # プレミア化件数（全体）
    n_premium = int(all_df.get("プレミア化", pd.Series(dtype=bool)).fillna(False).sum()) \
        if "プレミア化" in all_df.columns else 0

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("総件数", f"{len(ec_results)}件")
    m2.metric("表示中", f"{len(result_df)}件")
    if len(result_df) > 0 and "PT込利益" in result_df.columns:
        m3.metric("最大PT込利益", f"{int(result_df['PT込利益'].max()):,}円")
    # 外れ値件数
    if "最高値_外れ値" in result_df.columns:
        outlier_count = int(result_df["最高値_外れ値"].fillna(False).sum())
        m4.metric("⚠外れ値", f"{outlier_count}件",
                  help="最高買取価格が他店から乖離。実際は信頼買取価格で取引される可能性が高い")
    # 経路別サマリ (API / Scraper / Chrome拡張)
    m5.metric(
        "🧩Chrome拡張",
        f"{n_ext}件",
        delta=f"API {n_api} / Scr {n_scr}",
        delta_color="off",
        help="Chrome拡張経由で取得された価格の件数。0件なら拡張が動作していない可能性大",
    )
    # プレミア化件数
    m6.metric(
        "🔥プレミア化",
        f"{n_premium}件",
        help="定価より買取が高い希少化商品（0件の場合は premium_scan.py で再スキャン）",
    )

    # テーブル
    if "在庫状況" not in result_df.columns:
        result_df["在庫状況"] = "未確認"
    table_area = st.empty()
    _render_profit_table(table_area, result_df, PROFIT_DISPLAY_COLS)

    # Chrome拡張 0件警告
    if n_ext == 0 and (n_api > 0 or n_scr > 0):
        st.warning(
            "🧩 Chrome拡張からの価格取得が **0件** です。"
            "Chromeブラウザが起動しているか、拡張が reload されているか確認してください。"
            "詳しくは `python run.py --inspect-posts` で POST 履歴を確認できます。"
        )

    st.caption(
        "※ **ハイブリッド判定**: 利益 = 信頼買取価格(外れ値補正) - EC - 送料 ／ "
        "上振れ時利益 = 利益 + 上振れ余地(最高 - 信頼) ／ "
        "⚠ = 最高買取価格が他店から乖離している外れ値 (実際は信頼価格で取引される可能性大) ／ "
        "🔥 = 買取価格 > 定価 (希少化・プレミア化商品) ／ "
        "経路 🛰️API=楽天/Yahoo, 🕷️Scraper=Amazon/ヨドバシ等, 🧩拡張=Chrome拡張"
    )

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
