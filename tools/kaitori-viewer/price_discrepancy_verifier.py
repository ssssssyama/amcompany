"""キャッシュ内の EC最安値 と実商品ページ価格の乖離を自動検証する。

price_server や auto_extract が収集した価格は、ラベル誤抽出や楽天ショップの
JAN流用等で実ページと乖離することがある。このモジュールは:

1. cache_results.json の各エントリの EC URL を再訪問
2. 実ページから価格を抽出
3. キャッシュと実ページの価格差を比較
4. 乖離が閾値超えなら「要確認」フラグ or 自動削除

検出パターン:
- 価格乖離   : 実ページ価格 / キャッシュ価格 が 0.7〜1.3 範囲外
- ページ消失 : 404 / redirect to top / 検索0件等
- 商品不一致 : 商品名キーワードが実ページタイトルに含まれない
- 在庫切れ   : 実ページで「品切れ」「販売終了」検出

使い方:
    python price_discrepancy_verifier.py                 # 全件検証、レポート表示のみ
    python price_discrepancy_verifier.py --auto-remove   # 乖離エントリを自動削除
    python price_discrepancy_verifier.py --threshold 0.2 # 許容乖離率20%（デフォルト30%）
    python price_discrepancy_verifier.py --max 50        # 先頭50件だけ検証（高速確認用）
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")

CACHE_FILE = Path.home() / ".kaitori-viewer" / "cache_results.json"
REPORT_DIR = Path.home() / ".kaitori-viewer" / "logs"
DEFAULT_THRESHOLD = 0.30  # 30% 以上乖離 → 不一致判定
TIMEOUT_PER_ENTRY = 25


def _load_cache() -> list:
    if not CACHE_FILE.exists():
        return []
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _save_cache(data: list) -> None:
    try:
        # filelock があれば使用
        try:
            from filelock import FileLock
            lock = FileLock(str(CACHE_FILE) + ".lock", timeout=10)
        except ImportError:
            import contextlib
            lock = contextlib.nullcontext()
        with lock:
            tmp = CACHE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(CACHE_FILE)
    except OSError as e:
        logger.warning("キャッシュ保存失敗: %s", e)


def _similar_name(expected: str, actual: str, min_overlap: float = 0.3) -> bool:
    """商品名の類似度を簡易判定（英数トークンの重複率）"""
    import re as _re
    exp_tokens = set(t.upper() for t in _re.findall(r"[A-Za-z0-9]{2,}", expected or ""))
    act_tokens = set(t.upper() for t in _re.findall(r"[A-Za-z0-9]{2,}", actual or ""))
    if not exp_tokens:
        return True  # 型番がない商品名（ゲームタイトル等）はチェック省略
    overlap = exp_tokens & act_tokens
    return len(overlap) / len(exp_tokens) >= min_overlap


def verify_entry(entry: dict, browser, ctx, threshold: float = DEFAULT_THRESHOLD) -> dict:
    """1エントリを検証し、判定結果を返す。

    Returns:
        {
            "jan": str,
            "status": "ok" | "price_discrepancy" | "page_gone" | "name_mismatch"
                     | "out_of_stock" | "access_blocked" | "error",
            "cached_price": int,
            "fetched_price": int | None,
            "ratio": float | None,
            "reason": str,
            "page_title": str,
        }
    """
    jan = entry.get("JAN", "?")
    url = entry.get("EC URL") or entry.get("商品リンク") or ""
    cached_price = entry.get("EC最安値", 0) or 0
    product_name = entry.get("商品名", "")
    source = entry.get("ECソース", "?")

    result = {
        "jan": jan,
        "status": "error",
        "cached_price": cached_price,
        "fetched_price": None,
        "ratio": None,
        "reason": "",
        "page_title": "",
        "source": source,
        "product_name": product_name[:60],
    }

    if not url:
        result["status"] = "error"
        result["reason"] = "EC URLが空"
        return result

    try:
        from stealth import safe_goto
        from _worker_common import extract_selling_price

        page = ctx.new_page()
        try:
            # 同ドメインのルートをwarmup
            from urllib.parse import urlparse as _uparse
            parsed = _uparse(url)
            warmup = f"{parsed.scheme}://{parsed.netloc}/"
            ok = safe_goto(
                page, url, warmup_url=warmup,
                timeout=TIMEOUT_PER_ENTRY * 1000, max_retries=1,
                post_delay=(1.5, 3.0),
            )
            if not ok:
                result["status"] = "access_blocked"
                result["reason"] = "ページアクセス失敗（DNS/タイムアウト/anti-bot）"
                return result

            title = (page.title() or "")[:200]
            result["page_title"] = title
            body = page.text_content("body") or ""

            # 1. ページ消失 or リダイレクト判定
            gone_markers = [
                "商品がありません", "該当する商品はありません", "見つかりませんでした",
                "ページが移転", "利用できません", "404", "お探しのページ",
                "商品情報を取得できません",
            ]
            if any(m in title for m in gone_markers) or any(m in body[:2000] for m in gone_markers):
                result["status"] = "page_gone"
                result["reason"] = "ページが存在しない or リダイレクト"
                return result

            # 2. 在庫切れ判定
            stock_markers = ["販売終了", "取扱終了", "入荷待ち", "入荷未定",
                            "品切れ", "在庫なし", "現在ご購入いただけません"]
            in_stock_marker = ["カートに入れる", "今すぐ買う", "在庫あり", "ご注文できます"]
            body_sample = body[:5000]
            has_out = any(m in body_sample for m in stock_markers)
            has_in = any(m in body_sample for m in in_stock_marker)
            if has_out and not has_in:
                result["status"] = "out_of_stock"
                result["reason"] = "実ページで在庫切れ検出"
                return result

            # 3. 価格抽出と比較
            fetched = extract_selling_price(body)
            if not fetched:
                result["status"] = "error"
                result["reason"] = "実ページから価格抽出失敗"
                return result
            result["fetched_price"] = fetched

            if cached_price > 0:
                ratio = abs(fetched - cached_price) / cached_price
                result["ratio"] = round(ratio, 3)
                if ratio > threshold:
                    result["status"] = "price_discrepancy"
                    result["reason"] = (
                        f"キャッシュ {cached_price:,}円 vs 実ページ {fetched:,}円 "
                        f"(乖離 {ratio*100:.1f}% > {threshold*100:.0f}%)"
                    )
                    return result

            # 4. 商品名の型番一致チェック
            if product_name and not _similar_name(product_name, title):
                result["status"] = "name_mismatch"
                result["reason"] = f"タイトル「{title[:50]}」と商品名「{product_name[:30]}」の型番不一致"
                return result

            result["status"] = "ok"
            result["reason"] = f"実ページ価格 {fetched:,}円 が範囲内"
            return result

        finally:
            page.close()

    except Exception as e:
        result["status"] = "error"
        result["reason"] = f"例外: {str(e)[:100]}"
        return result


def verify_cache(threshold: float = DEFAULT_THRESHOLD, max_entries: int | None = None,
                 auto_remove: bool = False) -> dict:
    """キャッシュ全件を検証してレポートを返す。

    Args:
        threshold: 乖離許容率（例 0.30 なら ±30% 超えで異常判定）
        max_entries: 検証件数の上限（None なら全件）
        auto_remove: 異常判定のエントリをキャッシュから自動削除

    Returns:
        レポート dict
    """
    cache = _load_cache()
    if not cache:
        logger.info("キャッシュが空です")
        return {"total": 0, "ok": 0, "problems": []}

    if max_entries:
        cache = cache[:max_entries]

    logger.info("検証開始: %d件 (閾値 ±%.0f%%, 自動削除=%s)",
                len(cache), threshold * 100, auto_remove)

    from playwright.sync_api import sync_playwright
    from stealth import create_stealth_context, launch_stealth_browser

    problems = []
    ok_count = 0

    with sync_playwright() as p:
        browser = launch_stealth_browser(p, prefer="chromium")
        ctx = create_stealth_context(browser)

        for i, entry in enumerate(cache, 1):
            r = verify_entry(entry, browser, ctx, threshold=threshold)
            status = r["status"]
            if status == "ok":
                ok_count += 1
                logger.info("[%d/%d] ✅ %s (%s) %s",
                            i, len(cache), r["jan"], r["source"], r["reason"])
            else:
                problems.append(r)
                icon = {"page_gone": "🔗", "price_discrepancy": "💰",
                        "name_mismatch": "📛", "out_of_stock": "📦",
                        "access_blocked": "🚫", "error": "⚠"}.get(status, "❓")
                logger.warning("[%d/%d] %s %s (%s) %s: %s",
                               i, len(cache), icon, r["jan"], r["source"],
                               status, r["reason"])

        browser.close()

    # 自動削除
    if auto_remove and problems:
        # ページ消失・価格乖離・名前不一致・在庫切れは削除対象。access_blocked/error は残す（再試行余地）
        remove_statuses = {"page_gone", "price_discrepancy", "name_mismatch", "out_of_stock"}
        remove_jans = {p["jan"] for p in problems if p["status"] in remove_statuses}
        if remove_jans:
            full_cache = _load_cache()  # 検証中に変わっている可能性に備え再読み込み
            kept = [r for r in full_cache if r.get("JAN") not in remove_jans]
            _save_cache(kept)
            logger.warning("[自動削除] %d件のエントリをキャッシュから削除（残り %d→%d件）",
                           len(remove_jans), len(full_cache), len(kept))

    # レポート保存
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "threshold": threshold,
        "total": len(cache),
        "ok_count": ok_count,
        "problem_count": len(problems),
        "by_status": {},
        "problems": problems,
    }
    from collections import Counter
    status_counter = Counter(p["status"] for p in problems)
    report["by_status"] = dict(status_counter)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"discrepancy_{datetime.now().strftime('%Y%m%d%H%M')}.json"
    try:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        logger.info("レポート保存: %s", report_path)
    except OSError as e:
        logger.warning("レポート保存失敗: %s", e)

    return report


def _print_summary(report: dict) -> None:
    """レポートサマリを表示"""
    print("=" * 60)
    print(f"価格乖離検証レポート ({report.get('timestamp','?')})")
    print(f"  検証件数: {report['total']}件")
    print(f"  正常:     {report['ok_count']}件")
    print(f"  要対応:   {report['problem_count']}件")
    if report["by_status"]:
        print("  問題内訳:")
        icons = {"page_gone": "🔗 ページ消失", "price_discrepancy": "💰 価格乖離",
                 "name_mismatch": "📛 商品名不一致", "out_of_stock": "📦 在庫切れ",
                 "access_blocked": "🚫 アクセス不可", "error": "⚠ エラー"}
        for status, count in report["by_status"].items():
            print(f"    {icons.get(status, status)}: {count}件")
    if report["problems"]:
        print()
        print("  要対応エントリ (最大10件):")
        for p in report["problems"][:10]:
            print(f"    [{p['status']}] JAN={p['jan']} "
                  f"{p['product_name']} [{p.get('source','?')}]")
            print(f"       {p['reason']}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="価格乖離の自動検証")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"許容乖離率（デフォルト {DEFAULT_THRESHOLD}）")
    parser.add_argument("--max", type=int, default=None,
                        help="検証する最大件数")
    parser.add_argument("--auto-remove", action="store_true",
                        help="異常エントリをキャッシュから自動削除")
    args = parser.parse_args()

    t0 = time.time()
    report = verify_cache(
        threshold=args.threshold,
        max_entries=args.max,
        auto_remove=args.auto_remove,
    )
    elapsed = time.time() - t0
    logger.info("検証完了: %.1f秒", elapsed)
    _print_summary(report)

    # 異常があったら非0で終了
    sys.exit(0 if report["problem_count"] == 0 else 1)


if __name__ == "__main__":
    main()
