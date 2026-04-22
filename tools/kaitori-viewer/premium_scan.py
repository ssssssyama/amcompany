"""プレミア化商品の検出（買取価格 > 定価）

キャッシュ内のエントリ EC URL を再訪問して定価（メーカー希望小売価格）を取得し、
買取価格と比較してプレミア化（希少化）を判定する。

使い方:
    python premium_scan.py              # 全キャッシュを再スキャン
    python premium_scan.py --max 20     # 先頭20件のみ
    python premium_scan.py --update     # キャッシュに定価/プレミア化フラグを書き戻す

判定:
    プレミア化 = 最高買取価格 > 定価
    プレミア度 = 最高買取価格 / 定価
      1.0-1.2: 軽度
      1.2-1.5: 中度
      1.5+   : 高度（希少化確定）
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


def _load_cache() -> list:
    if not CACHE_FILE.exists():
        return []
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _save_cache(data: list) -> None:
    try:
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


def scan_premium(entries: list, ctx) -> list:
    """キャッシュエントリを実ページで再訪問し、定価を抽出してプレミア化判定を返す

    Returns:
        [{jan, 商品名, 最高買取価格, 定価, 買取_定価比, プレミア化, url, ...}]
    """
    from stealth import safe_goto
    from _worker_common import extract_msrp
    from urllib.parse import urlparse as _uparse

    results = []
    for i, entry in enumerate(entries, 1):
        jan = entry.get("JAN", "?")
        url = entry.get("EC URL") or entry.get("商品リンク") or ""
        max_kaitori = int(entry.get("最高買取価格", 0) or 0)
        product = entry.get("商品名", "")[:60]

        rec = {
            "jan": jan,
            "商品名": product,
            "最高買取価格": max_kaitori,
            "EC URL": url,
            "定価": None,
            "買取_定価比": None,
            "プレミア化": False,
            "プレミア度": None,
            "取得成功": False,
        }

        if not url or max_kaitori <= 0:
            logger.info("[%d/%d] ⏭ URL/買取価格無し %s", i, len(entries), jan)
            results.append(rec)
            continue

        page = ctx.new_page()
        try:
            parsed = _uparse(url)
            warmup = f"{parsed.scheme}://{parsed.netloc}/"
            ok = safe_goto(page, url, warmup_url=warmup,
                           timeout=25000, max_retries=1, post_delay=(1.5, 3.0))
            if not ok:
                logger.warning("[%d/%d] ❌ アクセス失敗 %s %s", i, len(entries), jan, url[:60])
                results.append(rec)
                continue
            body = page.text_content("body") or ""
            msrp = extract_msrp(body)
            if not msrp:
                logger.info("[%d/%d] ⚪ 定価未検出 %s", i, len(entries), jan)
                rec["取得成功"] = True
                results.append(rec)
                continue
            ratio = round(max_kaitori / msrp, 2)
            is_premium = max_kaitori > msrp
            # プレミア度分類
            if ratio >= 1.5:
                grade = "★★★ 高度"
            elif ratio >= 1.2:
                grade = "★★ 中度"
            elif ratio > 1.0:
                grade = "★ 軽度"
            else:
                grade = ""
            rec.update({
                "定価": msrp,
                "買取_定価比": ratio,
                "プレミア化": is_premium,
                "プレミア度": grade,
                "取得成功": True,
            })
            icon = "🔥" if is_premium else "  "
            logger.info(
                "[%d/%d] %s JAN=%s 買取%s円 vs 定価%s円 = %sx %s %s",
                i, len(entries), icon, jan,
                f"{max_kaitori:,}", f"{msrp:,}", ratio, grade, product[:30],
            )
        except Exception as e:
            logger.warning("[%d/%d] ⚠ %s: %s", i, len(entries), jan, str(e)[:100])
        finally:
            page.close()
            time.sleep(0.5)

        results.append(rec)
    return results


def update_cache_with_premium(scan_results: list) -> int:
    """スキャン結果をキャッシュに書き戻す（定価・プレミア化フラグを付加）"""
    cache = _load_cache()
    lookup = {r["jan"]: r for r in scan_results if r.get("取得成功")}
    updated = 0
    for r in cache:
        j = r.get("JAN")
        if j not in lookup:
            continue
        info = lookup[j]
        if info.get("定価"):
            r["定価"] = info["定価"]
            r["買取_定価比"] = info["買取_定価比"]
            r["プレミア化"] = bool(info["プレミア化"])
            updated += 1
    if updated:
        _save_cache(cache)
    return updated


def main():
    parser = argparse.ArgumentParser(description="プレミア化商品検出")
    parser.add_argument("--max", type=int, default=None, help="検証する最大件数")
    parser.add_argument("--update", action="store_true",
                        help="検出した定価・プレミア化フラグをキャッシュに書き戻す")
    parser.add_argument("--min-kaitori", type=int, default=5000,
                        help="対象とする最小買取価格（デフォルト5000円）")
    args = parser.parse_args()

    cache = _load_cache()
    if not cache:
        print("キャッシュが空です。先に auto_extract を実行してください")
        sys.exit(1)

    # 対象を絞る（買取価格 >= 閾値 かつ URL あり）
    targets = [
        r for r in cache
        if int(r.get("最高買取価格", 0) or 0) >= args.min_kaitori
        and (r.get("EC URL") or r.get("商品リンク"))
    ]
    if args.max:
        targets = targets[:args.max]

    logger.info("検証対象: %d / %d 件 (買取 >= %s円)",
                len(targets), len(cache), f"{args.min_kaitori:,}")

    from playwright.sync_api import sync_playwright
    from stealth import create_stealth_context, launch_stealth_browser

    t0 = time.time()
    with sync_playwright() as p:
        browser = launch_stealth_browser(p, prefer="chromium")
        ctx = create_stealth_context(browser)
        scan_results = scan_premium(targets, ctx)
        browser.close()

    premium = [r for r in scan_results if r.get("プレミア化")]
    logger.info("=" * 60)
    logger.info("検証完了: %.1f秒 / プレミア化 %d件 / 合計 %d件",
                time.time() - t0, len(premium), len(scan_results))

    # プレミア化商品を降順で表示
    premium_sorted = sorted(
        premium,
        key=lambda r: r.get("買取_定価比", 0) or 0,
        reverse=True,
    )
    print()
    print("=== プレミア化商品（買取価格 > 定価） ===")
    if not premium_sorted:
        print("  該当なし")
    for r in premium_sorted:
        print(
            f"  {r.get('プレミア度','')} 買取{r['最高買取価格']:,}円 / "
            f"定価{r['定価']:,}円 = {r['買取_定価比']}x "
            f"JAN={r['jan']} {r['商品名']}"
        )

    # レポート保存
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"premium_{datetime.now().strftime('%Y%m%d%H%M')}.json"
    report_path.write_text(
        json.dumps({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "scanned": len(scan_results),
            "premium_count": len(premium),
            "results": scan_results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("レポート保存: %s", report_path)

    if args.update:
        n = update_cache_with_premium(scan_results)
        logger.info("キャッシュ更新: %d件に定価/プレミア化フラグを書き戻し", n)

    sys.exit(0)


if __name__ == "__main__":
    main()
