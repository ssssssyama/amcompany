"""CDP接続ワーカー用の共通ボイラープレート

ブロック済みリテーラー（ビックカメラ、ジョーシン等）のワーカーが使う
CDP接続→フォールバック→JSON出力の共通処理を提供する。

使い方（各ワーカーから）:
    from _cdp_worker_common import run_worker

    def search(context, jan_code):
        # ... 検索ロジック ...
        return result_dict or None

    run_worker(search)
"""

import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

_USE_CDP = os.environ.get("KAITORI_NO_CDP", "").lower() not in ("1", "true", "yes")


def run_worker(worker_fn, extra_headers=None, retailer_domain=None):
    """CDPワーカーのエントリポイント。

    1. 同一リテーラードメインへの連続アクセスを rate limit で間引く
    2. CDP接続を試行（Brave/Chrome）
    3. 失敗時はPlaywright直接起動にフォールバック
    4. worker_fn(context, jan_code) を呼び出し
    5. 結果をJSON出力（bot検出ページに変遷していたらnull）

    Args:
        worker_fn: (context, jan_code: str) -> dict | None
        extra_headers: コンテキストに追加するHTTPヘッダ（Referer等）
        retailer_domain: rate limit キー（例 "www.biccamera.com"）
    """
    jan_code = sys.argv[1]

    try:
        from playwright.sync_api import sync_playwright
        from stealth import (
            create_cdp_stealth_context, create_stealth_context,
            _rate_limit_wait, _is_blocked_page,
        )

        # 同一リテーラーへのアクセス間隔を確保（429/bot検出回避）
        if retailer_domain:
            _rate_limit_wait(retailer_domain)

        ctx_kwargs = {}
        if extra_headers:
            ctx_kwargs["extra_http_headers"] = extra_headers

        with sync_playwright() as p:
            cdp_connected = False
            if _USE_CDP:
                try:
                    from _cdp_browser import CDP_ENDPOINT, ensure_cdp_chrome
                    if ensure_cdp_chrome():
                        browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                        cdp_connected = True
                except Exception as e:
                    print(f"CDP接続失敗、従来モードにフォールバック: {e}", file=sys.stderr)

            if not cdp_connected:
                browser = p.chromium.launch(headless=True, timeout=15000)

            try:
                if cdp_connected:
                    context = create_cdp_stealth_context(browser, **ctx_kwargs)
                else:
                    context = create_stealth_context(browser, **ctx_kwargs)

                try:
                    result = worker_fn(context, jan_code)
                    # Bot検出ページに変遷していないかの追加チェック
                    # （worker_fn は既に正常結果か null を返すが、万一検出ページが
                    #  商品情報として採用されないよう final safety net として検証）
                    if result and isinstance(result, dict):
                        name = (result.get("name") or "")
                        if any(m in name for m in ("Human Verification", "Access Denied", "Bot Challenge", "Attention Required")):
                            print(f"bot detection leaked into result: {name[:50]}", file=sys.stderr)
                            result = None
                finally:
                    context.close()
            finally:
                browser.close()

        print(json.dumps(result, ensure_ascii=False) if result else "null")

    except Exception as e:
        print("null")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
