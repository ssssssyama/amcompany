"""楽天市場 / Yahoo!ショッピング の利益商品を自動でお気に入り追加する

cache_results.json から ECソース が「楽天」または「Yahoo」で現金利益がある
商品を抽出し、Playwrightで商品ページを訪問して「お気に入り登録」ボタンを
クリックする。

初回実行: --headed でログインブラウザが立ち上がるので、各サイトで
          手動ログイン。認証情報は ~/.kaitori-viewer/favorite_state_*.json に保存。
2回目以降: storage_state で自動ログインを試み、失敗時は headful に自動フォールバック。

重複防止: ~/.kaitori-viewer/favorite_added.json に (JAN, source, url) を記録。
         同一 URL は再度追加しない。

使い方:
    python favorite_adder.py                    # 利益商品全件を追加（要初回ログイン）
    python favorite_adder.py --dry-run          # 追加せず対象だけリスト表示
    python favorite_adder.py --min-profit 5000  # 現金利益5000円以上のみ
    python favorite_adder.py --source 楽天      # 楽天のみ
    python favorite_adder.py --max 10           # 先頭10件だけ
    python favorite_adder.py --reset            # 保存された認証情報とお気に入り履歴をクリア
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")

CACHE_FILE = Path.home() / ".kaitori-viewer" / "cache_results.json"
DATA_DIR = Path.home() / ".kaitori-viewer"
ADDED_FILE = DATA_DIR / "favorite_added.json"

# 安全装置: 1日あたり追加できる上限（アカウント凍結リスク軽減）
DAILY_LIMIT_DEFAULT = 20
# ソース別のインターバル（秒）。連続追加でサイト側のbot検知を回避
INTER_ITEM_DELAY_SEC = 3.0

# サイト別の認証情報保存先（storage_state）
STATE_FILES = {
    "楽天": DATA_DIR / "favorite_state_rakuten.json",
    "Yahoo": DATA_DIR / "favorite_state_yahoo.json",
}

# ログインチェック用 URL とログイン完了判定テキスト
LOGIN_CHECK = {
    "楽天": {
        # my.rakuten.co.jp にアクセス: ログイン済みなら「マイページ」、未ログインなら
        # ログインフォームにリダイレクトされる。URL/title で確実判定できる。
        "home": "https://my.rakuten.co.jp/",
        "logged_in_marker": "ログアウト",  # ログイン済みのみ表示される
        "logged_out_marker": "ユーザID",   # ログインフォームに出る文字
    },
    "Yahoo": {
        "home": "https://shopping.yahoo.co.jp/",
        "logged_in_marker": "さん",  # "○○さん" がヘッダーに出る
        "logged_out_marker": "ログイン",
    },
}

# 「お気に入り登録」ボタンセレクタ候補（クリック順に試す）
FAVORITE_BUTTON_SELECTORS = {
    "楽天": [
        # 楽天市場は「ブックマーク」(bookmark) と呼ぶ。
        # 商品ページの標準ブックマーク追加ボタンは a.addBkm
        ".itemBookmarkAreaWrapper a.addBkm",
        ".itemBookmarkArea a.addBkm",
        ".floatBookmarkArea a.addBkm",
        "a.addBkm",
        "a.favButton",
        "button[class*='favorite']",
        "a[href*='favorite']",
        "button:has-text('お気に入り登録')",
        "a:has-text('ブックマーク')",
        "button:has-text('お気に入り')",
    ],
    "Yahoo": [
        "button[class*='Favorite']",
        "button[data-ylk*='favorite']",
        "[data-testid='favorite-button']",
        "button:has-text('お気に入り')",
        "button:has-text('気になる')",
    ],
}

# 「お気に入り登録完了」の判定テキスト（クリック後に表示されたら成功）
SUCCESS_MARKERS = [
    "お気に入りに追加しました",
    "お気に入り登録しました",
    "お気に入りに追加",
    "登録しました",
    "気になるリストに追加",
    "ブックマークに追加",
    "ブックマークしました",
]


def _load_cache() -> list:
    if not CACHE_FILE.exists():
        return []
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _load_added() -> dict:
    """既にお気に入りに追加した履歴 { 'source|jan': {'ts':..., 'url':...} }"""
    if not ADDED_FILE.exists():
        return {}
    try:
        return json.loads(ADDED_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_added(data: dict) -> None:
    ADDED_FILE.parent.mkdir(parents=True, exist_ok=True)
    ADDED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def _count_added_today(added: dict) -> int:
    """今日追加した件数を返す（日次上限判定用）"""
    today = datetime.now().strftime("%Y-%m-%d")
    count = 0
    for rec in added.values():
        ts = rec.get("ts", "")
        if ts.startswith(today):
            count += 1
    return count


def _is_logged_in(page, source: str) -> bool:
    """ログイン済みかを判定

    楽天: my.rakuten.co.jp にアクセス → ログインフォームにリダイレクトされず
          body に「ログアウト」が含まれていればログイン済み
    Yahoo: ヘッダーに「○○さん」表示 or 「ログアウト」リンク
    """
    info = LOGIN_CHECK[source]
    try:
        current_url = page.url
        # 楽天: ログインフォームへのリダイレクト検出
        if source == "楽天":
            cu_lower = current_url.lower()
            # ログイン/認証関連URL → 未ログイン
            if any(k in cu_lower for k in ("login.", "/login", "/auth", "signin", "sso/authorize")):
                return False
            body = (page.text_content("body") or "")
            # ログアウトリンクが存在 = ログイン済み（最も強いシグナル）
            if "ログアウト" in body[:10000]:
                return True
            # my.rakuten.co.jp / member.rakuten.co.jp のドメインに到達している場合
            # （リダイレクトされなかった = ログイン済みの可能性大）
            if "my.rakuten.co.jp" in current_url and "ログイン" not in body[:3000]:
                return True
            # 会員ページ特有の文言
            if any(w in body[:5000] for w in ("楽天ポイント", "マイページトップ", "お買い物履歴")):
                return True
            return False
        # Yahoo: ヘッダーの「○○さん」or「ログアウト」で判定
        if source == "Yahoo":
            body = (page.text_content("body") or "")[:5000]
            if "ログアウト" in body:
                return True
            if re.search(r"[^\s]+さん", body[:1500]):
                return True
            return False
    except Exception:
        pass
    return False


def _select_candidates(
    cache: list,
    min_profit: int = 1,
    source_filter: str | None = None,
    already_added: dict | None = None,
) -> list:
    """お気に入り追加対象となるエントリを抽出"""
    already_added = already_added or {}
    candidates = []
    for r in cache:
        source = r.get("ECソース", "")
        if source not in ("楽天", "Yahoo"):
            continue
        if source_filter and source != source_filter:
            continue
        profit = r.get("現金利益", 0) or 0
        if profit < min_profit:
            continue
        url = r.get("EC URL") or r.get("商品リンク") or ""
        if not url:
            continue
        key = f"{source}|{r.get('JAN','?')}"
        if key in already_added:
            continue  # 追加済み
        candidates.append(r)
    # 利益降順
    candidates.sort(key=lambda r: r.get("PT込利益", 0) or r.get("現金利益", 0), reverse=True)
    return candidates


def _ensure_login(ctx, source: str, login_wait_sec: int = 180, headless: bool = True) -> bool:
    """ログイン状態を確認。未ログインかつheadlessなら失敗、headfulなら待機"""
    info = LOGIN_CHECK[source]
    page = ctx.new_page()
    try:
        page.goto(info["home"], wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        if _is_logged_in(page, source):
            logger.info("[%s] ログイン済み", source)
            return True
        if headless:
            logger.error("[%s] 未ログイン & headless → 初回は --headed で実行してください", source)
            return False
        logger.info("[%s] ブラウザでログインしてください（最大%d秒待機）", source, login_wait_sec)
        deadline = time.time() + login_wait_sec
        while time.time() < deadline:
            time.sleep(3)
            try:
                if _is_logged_in(page, source):
                    logger.info("[%s] ログイン完了を検知", source)
                    return True
            except Exception:
                pass
        logger.error("[%s] ログインタイムアウト", source)
        return False
    finally:
        page.close()


def _click_favorite(page, source: str) -> bool:
    """お気に入り登録ボタンをクリックし、成功判定して True/False を返す

    同じセレクタで複数要素がマッチする場合 (楽天の floating/float/item の
    3つの bookmark area 等) 、可視の要素を選んでクリックする。
    """
    selectors = FAVORITE_BUTTON_SELECTORS.get(source, [])
    for sel in selectors:
        try:
            elements = page.query_selector_all(sel)
            for el in elements:
                try:
                    if not el.is_visible():
                        continue
                except Exception:
                    continue
                try:
                    el.scroll_into_view_if_needed(timeout=3000)
                except Exception:
                    pass
                page.wait_for_timeout(400)
                try:
                    el.click(timeout=5000)
                except Exception as e:
                    # click failed (例: overlay等); JSクリックにフォールバック
                    try:
                        page.evaluate("(e) => e.click()", el)
                    except Exception:
                        logger.debug("[%s] クリック失敗 sel=%s: %s", source, sel, str(e)[:60])
                        continue
                page.wait_for_timeout(1800)
                # 成功判定: body に success marker 出現
                body = (page.text_content("body") or "")[:5000]
                if any(m in body for m in SUCCESS_MARKERS):
                    return True
                # ボタンの aria-pressed / aria-checked / class で判定
                try:
                    pressed = el.get_attribute("aria-pressed")
                    if pressed == "true":
                        return True
                    cls = el.get_attribute("class") or ""
                    # 楽天は登録後 a.addBkm が a.delBkm に変わる
                    if "delBkm" in cls or "active" in cls or "registered" in cls.lower():
                        return True
                except Exception:
                    pass
                # 登録直後に a.delBkm が現れたらOK（DOM全体を再確認）
                if page.query_selector("a.delBkm"):
                    return True
                # クリックは通った。成功マーカーが出なくても True 扱い（ボタン見つからずよりマシ）
                return True
        except Exception as e:
            logger.debug("[%s] セレクタ %s 失敗: %s", source, sel, str(e)[:60])
            continue
    return False


def _add_favorites_for_source(
    source: str, items: list, headless: bool, dry_run: bool,
    login_wait_sec: int = 180,
) -> list:
    """1つのECソースに対して、複数商品のお気に入り登録を行う

    Returns:
        成功したエントリのリスト（{'JAN':..., 'url':..., 'ts':...}）
    """
    if not items:
        return []
    logger.info("=== %s: %d件対象 ===", source, len(items))
    if dry_run:
        for it in items[:20]:
            profit = it.get("現金利益", 0) or 0
            logger.info("[dry-run] %s %+s円 %s",
                        it.get("JAN"), f"{profit:,}",
                        it.get("商品名", "")[:40])
        if len(items) > 20:
            logger.info("[dry-run] ... 他%d件", len(items) - 20)
        return []

    from playwright.sync_api import sync_playwright
    from stealth import create_stealth_context, launch_stealth_browser, safe_goto

    state_file = STATE_FILES[source]
    added_records = []

    with sync_playwright() as p:
        browser = launch_stealth_browser(p, prefer="chromium", headless=headless)
        ctx_kwargs = {
            "accept_downloads": True,
            "viewport": {"width": 1280, "height": 900},
            "locale": "ja-JP",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        if state_file.exists():
            ctx_kwargs["storage_state"] = str(state_file)
            logger.info("[%s] 認証情報ロード: %s", source, state_file.name)

        context = browser.new_context(**ctx_kwargs)

        try:
            # ログイン確認
            if not _ensure_login(context, source, login_wait_sec=login_wait_sec, headless=headless):
                return []
            # 認証情報を保存（ログイン後にトークンが更新されている可能性）
            try:
                state_file.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(state_file))
                logger.info("[%s] 認証情報を保存", source)
            except Exception as e:
                logger.warning("[%s] 認証保存失敗: %s", source, e)

            # 各商品を訪問してお気に入り登録
            for i, item in enumerate(items, 1):
                jan = item.get("JAN", "?")
                url = item.get("EC URL") or item.get("商品リンク") or ""
                if not url:
                    continue
                page = context.new_page()
                try:
                    from urllib.parse import urlparse as _uparse
                    parsed = _uparse(url)
                    warmup = f"{parsed.scheme}://{parsed.netloc}/"
                    ok = safe_goto(
                        page, url, warmup_url=warmup,
                        timeout=25000, max_retries=1, post_delay=(2.0, 3.5),
                    )
                    if not ok:
                        logger.warning("[%d/%d] ❌ アクセス失敗 %s %s", i, len(items), jan, url[:60])
                        continue
                    # ページが商品ページか軽くチェック
                    body_len = len(page.text_content("body") or "")
                    if body_len < 500:
                        logger.warning("[%d/%d] ❌ ページ空 %s", i, len(items), jan)
                        continue
                    # お気に入り登録クリック
                    success = _click_favorite(page, source)
                    if success:
                        logger.info("[%d/%d] ⭐ お気に入り追加 %s %s", i, len(items), jan,
                                    item.get("商品名", "")[:40])
                        added_records.append({
                            "jan": jan,
                            "source": source,
                            "url": url,
                            "ts": datetime.now().isoformat(timespec="seconds"),
                            "profit": item.get("現金利益", 0),
                            "product_name": item.get("商品名", "")[:60],
                        })
                    else:
                        logger.warning("[%d/%d] ⚠ ボタン見つからず %s", i, len(items), jan)
                except Exception as e:
                    logger.warning("[%d/%d] ⚠ エラー %s: %s", i, len(items), jan, str(e)[:80])
                finally:
                    page.close()
                # 連続追加でレート制限/bot検知に引っかからないようインターバル
                time.sleep(INTER_ITEM_DELAY_SEC)

            # 最終 storage_state 更新
            try:
                context.storage_state(path=str(state_file))
            except Exception:
                pass

        finally:
            context.close()
            browser.close()

    return added_records


def add_favorites(
    min_profit: int = 1,
    source_filter: str | None = None,
    max_items: int | None = None,
    dry_run: bool = False,
    headless: bool = True,
    login_wait_sec: int = 180,
    daily_limit: int = DAILY_LIMIT_DEFAULT,
) -> dict:
    """メインエントリ: キャッシュから利益商品を抽出してお気に入り追加

    Args:
        daily_limit: 1日あたり追加上限（アカウント凍結リスク軽減のため
                     連続大量追加を防ぐ。0 なら無制限）
    """
    cache = _load_cache()
    if not cache:
        logger.info("キャッシュが空です")
        return {"added": 0, "skipped": 0}

    already = _load_added()

    # 日次上限チェック
    today_count = _count_added_today(already)
    if daily_limit > 0 and today_count >= daily_limit:
        logger.warning(
            "日次上限到達: 今日すでに %d 件追加済み（上限 %d）。"
            "これ以上はアカウント凍結リスクがあるため追加を中止します。",
            today_count, daily_limit,
        )
        return {"added": 0, "skipped": 0, "daily_limit_reached": True,
                "today_count": today_count}

    candidates = _select_candidates(cache, min_profit=min_profit,
                                    source_filter=source_filter,
                                    already_added=already)
    # 日次上限まで追加するよう max_items を調整
    remaining_today = (daily_limit - today_count) if daily_limit > 0 else len(candidates)
    effective_max = min(max_items, remaining_today) if max_items else remaining_today
    if effective_max < len(candidates):
        logger.info("日次残数 %d 件に制限（候補 %d 件 / 本日追加済 %d 件 / 上限 %d 件）",
                    effective_max, len(candidates), today_count, daily_limit)
        candidates = candidates[:effective_max]

    logger.info("対象: %d件 (すでに追加済み %d件を除外)", len(candidates), len(already))
    if not candidates:
        return {"added": 0, "skipped": 0}

    # ソース別にグループ化
    by_source = {"楽天": [], "Yahoo": []}
    for r in candidates:
        by_source[r["ECソース"]].append(r)

    total_added = 0
    for source, items in by_source.items():
        if not items:
            continue
        added = _add_favorites_for_source(
            source, items, headless=headless, dry_run=dry_run,
            login_wait_sec=login_wait_sec,
        )
        for rec in added:
            already[f"{rec['source']}|{rec['jan']}"] = rec
        total_added += len(added)

    if not dry_run:
        _save_added(already)

    return {
        "added": total_added,
        "candidates": len(candidates),
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser(description="楽天/Yahoo利益商品のお気に入り自動追加")
    parser.add_argument("--min-profit", type=int, default=1,
                        help="対象とする最小現金利益（円）")
    parser.add_argument("--source", choices=["楽天", "Yahoo"], default=None,
                        help="特定ソースのみ処理")
    parser.add_argument("--max", type=int, default=None,
                        help="追加する最大件数")
    parser.add_argument("--dry-run", action="store_true",
                        help="追加せず対象のみ表示")
    parser.add_argument("--headed", action="store_true",
                        help="ヘッドフル起動（初回ログイン用）")
    parser.add_argument("--login-wait", type=int, default=180,
                        help="手動ログイン待機秒数")
    parser.add_argument("--reset", action="store_true",
                        help="認証情報とお気に入り履歴をクリア")
    parser.add_argument("--daily-limit", type=int, default=DAILY_LIMIT_DEFAULT,
                        help=f"1日あたりの追加上限（デフォルト {DAILY_LIMIT_DEFAULT}, 0で無制限）")
    args = parser.parse_args()

    if args.reset:
        cleared = []
        for f in list(STATE_FILES.values()) + [ADDED_FILE]:
            if f.exists():
                f.unlink()
                cleared.append(str(f))
        print("クリア:", cleared)
        sys.exit(0)

    headless = not args.headed
    result = add_favorites(
        min_profit=args.min_profit,
        source_filter=args.source,
        max_items=args.max,
        dry_run=args.dry_run,
        headless=headless,
        login_wait_sec=args.login_wait,
        daily_limit=args.daily_limit,
    )
    # ヘッドレスでログイン失敗 → ヘッドフルに自動フォールバック
    if (not args.dry_run and headless and result["added"] == 0
            and result.get("candidates", 0) > 0):
        logger.warning("ヘッドレスで0件追加 → ヘッドフルで再試行")
        result = add_favorites(
            min_profit=args.min_profit, source_filter=args.source,
            max_items=args.max, dry_run=False, headless=False,
            login_wait_sec=args.login_wait,
        )
    print(f"結果: {result}")
    sys.exit(0 if result["added"] > 0 or args.dry_run else 1)


if __name__ == "__main__":
    main()
