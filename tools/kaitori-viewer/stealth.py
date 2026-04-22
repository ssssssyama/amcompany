"""Playwright bot検出対策の共通設定

Chromium / Firefox でステルススクリプトを分岐し、
headless検出・フィンガープリント対策を包括的に適用する。
"""

# --- Chromium 用ステルススクリプト ---
_CHROMIUM_STEALTH_JS = """
// 1. webdriver フラグ除去
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// 2. languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['ja-JP', 'ja', 'en-US', 'en'],
});

// 3. plugins — 現代の Chrome は空の PluginArray を返す。
//    デフォルトの空 PluginArray をそのまま使うのが最も安全なため上書きしない。

// 4. window.chrome — 既存オブジェクトを壊さず不足分だけ補完
(function() {
    if (!window.chrome) window.chrome = {};
    if (!window.chrome.runtime) {
        window.chrome.runtime = {
            connect: function() { return {onMessage: {addListener: function(){}}, postMessage: function(){}, disconnect: function(){}}; },
            sendMessage: function(msg, cb) { if (cb) cb(); },
            onMessage: {addListener: function(){}, removeListener: function(){}},
            onConnect: {addListener: function(){}, removeListener: function(){}},
            getManifest: function() { return {}; },
        };
    }
    if (!window.chrome.csi) {
        window.chrome.csi = function() { return {startE: Date.now(), onloadT: Date.now(), pageT: 0}; };
    }
    if (!window.chrome.loadTimes) {
        window.chrome.loadTimes = function() {
            return {commitLoadTime: Date.now() / 1000, connectionInfo: 'http/1.1', finishDocumentLoadTime: Date.now() / 1000,
                    finishLoadTime: Date.now() / 1000, firstPaintAfterLoadTime: 0, firstPaintTime: Date.now() / 1000,
                    navigationType: 'Other', npnNegotiatedProtocol: 'unknown', requestTime: Date.now() / 1000,
                    startLoadTime: Date.now() / 1000, wasAlternateProtocolAvailable: false, wasFetchedViaSpdy: false,
                    wasNpnNegotiated: false};
        };
    }
})();

// 5. WebGL — SwiftShader (headless のデフォルト) を隠す
(function() {
    const VENDOR = 'Google Inc. (NVIDIA)';
    const RENDERER = 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)';
    function patchCtx(proto) {
        if (!proto) return;
        const orig = proto.getParameter;
        proto.getParameter = function(param) {
            if (param === 37445) return VENDOR;
            if (param === 37446) return RENDERER;
            return orig.call(this, param);
        };
    }
    patchCtx(WebGLRenderingContext.prototype);
    if (typeof WebGL2RenderingContext !== 'undefined') {
        patchCtx(WebGL2RenderingContext.prototype);
    }
})();

// 6. Permissions API — headless では notifications が常に denied
(function() {
    if (typeof Permissions !== 'undefined' && Permissions.prototype.query) {
        const origQuery = Permissions.prototype.query;
        Permissions.prototype.query = function(desc) {
            if (desc && desc.name === 'notifications') {
                return Promise.resolve({state: Notification.permission || 'prompt', onchange: null});
            }
            return origQuery.call(this, desc);
        };
    }
})();

// 7. outerHeight / outerWidth — headless だと 0 になる場合がある
if (window.outerHeight === 0) {
    Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight + 85});
}
if (window.outerWidth === 0) {
    Object.defineProperty(window, 'outerWidth', {get: () => window.innerWidth});
}

// 8. Playwright / CDP の痕跡を除去
(function() {
    for (const prop of Object.getOwnPropertyNames(window)) {
        if (/^cdc_/.test(prop) || /^__playwright/.test(prop)) {
            try { delete window[prop]; } catch(e) {}
        }
    }
})();

// 9. iframe contentWindow 対策 (一部の検出スクリプトが利用)
(function() {
    try {
        const origCreate = document.createElement.bind(document);
        const handler = {
            apply: function(target, thisArg, args) {
                const el = Reflect.apply(target, thisArg, args);
                if (args[0] && args[0].toLowerCase() === 'iframe') {
                    el.addEventListener('load', function() {
                        try {
                            Object.defineProperty(el.contentWindow.navigator, 'webdriver', {get: () => undefined});
                        } catch(e) {}
                    });
                }
                return el;
            }
        };
        document.createElement = new Proxy(origCreate, handler);
    } catch(e) {}
})();
"""

# --- Firefox 用ステルススクリプト ---
_FIREFOX_STEALTH_JS = """
// 1. webdriver フラグ除去
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// 2. languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['ja-JP', 'ja', 'en-US', 'en'],
});

// 3. plugins — Firefox もデフォルトの空 PluginArray で OK。上書きしない。

// 4. window.chrome は Firefox に存在しないので触らない。

// 5. WebGL — Firefox は vendor を 'Mozilla' と報告する
(function() {
    const VENDOR = 'Mozilla';
    const RENDERER = 'NVIDIA GeForce GTX 1650 SUPER';
    function patchCtx(proto) {
        if (!proto) return;
        const orig = proto.getParameter;
        proto.getParameter = function(param) {
            if (param === 37445) return VENDOR;
            if (param === 37446) return RENDERER;
            return orig.call(this, param);
        };
    }
    patchCtx(WebGLRenderingContext.prototype);
    if (typeof WebGL2RenderingContext !== 'undefined') {
        patchCtx(WebGL2RenderingContext.prototype);
    }
})();

// 6. Permissions API
(function() {
    if (typeof Permissions !== 'undefined' && Permissions.prototype.query) {
        const origQuery = Permissions.prototype.query;
        Permissions.prototype.query = function(desc) {
            if (desc && desc.name === 'notifications') {
                return Promise.resolve({state: 'prompt', onchange: null});
            }
            return origQuery.call(this, desc);
        };
    }
})();

// 7. outerHeight / outerWidth
if (window.outerHeight === 0) {
    Object.defineProperty(window, 'outerHeight', {get: () => window.innerHeight + 85});
}
if (window.outerWidth === 0) {
    Object.defineProperty(window, 'outerWidth', {get: () => window.innerWidth});
}

// 8. Playwright の痕跡を除去
(function() {
    for (const prop of Object.getOwnPropertyNames(window)) {
        if (/^__playwright/.test(prop)) {
            try { delete window[prop]; } catch(e) {}
        }
    }
})();
"""


def _stealth_defaults(**kwargs):
    """ステルスコンテキスト用のデフォルト設定を生成する（内部共有）"""
    import random

    widths = [1366, 1440, 1536, 1600, 1920]
    heights = [768, 900, 864, 900, 1080]
    idx = random.randint(0, len(widths) - 1)

    defaults = {
        "viewport": {"width": widths[idx], "height": heights[idx]},
        "locale": "ja-JP",
        "timezone_id": "Asia/Tokyo",
        "extra_http_headers": {
            "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        },
    }
    defaults.update(kwargs)
    return defaults


def create_stealth_context(browser, **kwargs):
    """bot検出を回避するブラウザコンテキストを作成する

    ブラウザ種別（Chromium/Firefox）を自動判定し、適切なステルス
    スクリプトを注入する。User-Agent はブラウザ本来の値を使用する
    （バージョン不一致によるフィンガープリント検出を回避）。
    """
    browser_name = getattr(getattr(browser, "browser_type", None), "name", "chromium")

    context = browser.new_context(**_stealth_defaults(**kwargs))

    if browser_name == "firefox":
        context.add_init_script(_FIREFOX_STEALTH_JS)
    else:
        context.add_init_script(_CHROMIUM_STEALTH_JS)

    return context


def create_cdp_stealth_context(browser, **kwargs):
    """CDP接続された実Chrome用のステルスコンテキストを作成する

    実Chromeは TLS/HTTP2 指紋が正規のため、プロトコルレベル検知は不要。
    JS層のステルス（webdriver除去等）とビューポートランダム化のみ適用する。
    """
    context = browser.new_context(**_stealth_defaults(**kwargs))
    context.add_init_script(_CHROMIUM_STEALTH_JS)
    return context


# --- アクセス遮断対策: warmup + retry + rate limit ---
import os as _os
import random as _random
import time as _time
from pathlib import Path as _Path
from urllib.parse import urlparse as _urlparse

_RATE_LIMIT_FILE = _Path.home() / ".kaitori-viewer" / ".domain_rate_limit.json"
_MIN_DOMAIN_INTERVAL = 2.0  # 同一ドメインへの最小アクセス間隔（秒）

# Bot検出ページを示すマーカー（タイトル or URL パターン）
_BLOCKED_MARKERS = (
    "Human Verification",
    "Attention Required",
    "Access Denied",
    "Error 403",
    "Bot Challenge",
    "Are you a robot",
    "Just a moment",
    "Checking your browser",
    "不正アクセス",
    "ロボット",
)

# 遮断系ネットワークエラー
_BLOCKING_ERRORS = (
    "ERR_HTTP2_PROTOCOL_ERROR",
    "NS_ERROR_NET_INTERRUPT",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_CLOSED",
    "ERR_CONNECTION_REFUSED",
    "ERR_EMPTY_RESPONSE",
    "ERR_FAILED",
)


def _domain_of(url: str) -> str:
    try:
        return _urlparse(url).netloc
    except Exception:
        return ""


def _rate_limit_wait(domain: str) -> None:
    """同一ドメインへの連続アクセスを間引く（ファイル共有で複数サブプロセス対応）"""
    if not domain:
        return
    try:
        import json as _json
        _RATE_LIMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if _RATE_LIMIT_FILE.exists():
            try:
                data = _json.loads(_RATE_LIMIT_FILE.read_text(encoding="utf-8"))
            except (OSError, _json.JSONDecodeError):
                data = {}
        last = float(data.get(domain, 0))
        now = _time.time()
        wait = _MIN_DOMAIN_INTERVAL - (now - last)
        if wait > 0:
            _time.sleep(wait)
        data[domain] = _time.time()
        # 古いエントリは削除（24h超）
        cutoff = _time.time() - 86400
        data = {k: v for k, v in data.items() if float(v) > cutoff}
        _RATE_LIMIT_FILE.write_text(_json.dumps(data), encoding="utf-8")
    except OSError:
        pass  # ファイル書き込み失敗でも続行


def _is_blocked_page(page) -> bool:
    """ページが bot検出ページに変遷したかを判定"""
    try:
        title = (page.title() or "")
        if any(m in title for m in _BLOCKED_MARKERS):
            return True
        body = (page.text_content("body") or "")[:500]
        if any(m in body for m in _BLOCKED_MARKERS):
            return True
    except Exception:
        pass
    return False


def _is_blocking_error(err_str: str) -> bool:
    """エラーメッセージが遮断系か判定"""
    return any(m in err_str for m in _BLOCKING_ERRORS)


def safe_goto(
    page,
    url: str,
    warmup_url: str | None = None,
    wait_until: str = "domcontentloaded",
    timeout: int = 30000,
    max_retries: int = 2,
    post_delay: tuple[float, float] = (2.0, 4.0),
) -> bool:
    """Bot遮断対策込みのページ遷移。

    1. 同一ドメインへの連続アクセスを rate limit で間引く
    2. warmup_url が指定されていれば先にホームページを訪問しcookies確立
    3. ターゲットURLへ遷移、遮断エラーならバックオフしてリトライ
    4. ページが bot検出ページに変遷していたら False

    Args:
        page: Playwright page
        url: ターゲットURL
        warmup_url: 事前訪問URL（同ドメインのトップページ推奨）
        wait_until: goto の wait_until
        timeout: goto のタイムアウト（ms）
        max_retries: リトライ回数（0ならリトライなし）
        post_delay: goto 後のランダム遅延範囲（秒）

    Returns:
        True=成功（Bot検出ページでもない）, False=失敗
    """
    domain = _domain_of(url)
    _rate_limit_wait(domain)

    # warmup: ホームページ訪問でcookies/session確立
    if warmup_url and warmup_url != url:
        try:
            page.goto(warmup_url, wait_until="domcontentloaded", timeout=timeout)
            _time.sleep(_random.uniform(1.5, 3.0))
        except Exception:
            pass  # warmup失敗でも続行

    last_err = ""
    for attempt in range(max_retries + 1):
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
            # ページ描画を待つ
            _time.sleep(_random.uniform(*post_delay))
            # Bot検出ページに変遷していないか確認
            if _is_blocked_page(page):
                last_err = "bot detection page"
                if attempt < max_retries:
                    _time.sleep(_random.uniform(4.0, 8.0))  # 長めのバックオフ
                    continue
                return False
            return True
        except Exception as e:
            last_err = str(e)[:200]
            if _is_blocking_error(last_err) and attempt < max_retries:
                _time.sleep(_random.uniform(3.0, 6.0) * (attempt + 1))  # 指数バックオフ
                continue
            if attempt >= max_retries:
                import sys as _sys
                print(f"safe_goto failed ({url[:80]}): {last_err}", file=_sys.stderr)
                return False
    return False


def launch_stealth_browser(playwright, prefer: str = "chromium", headless: bool = True):
    """ステルス設定付きブラウザを起動（fallback付き）

    Args:
        playwright: sync_playwright コンテキスト
        prefer: 'chromium' or 'firefox'
        headless: ヘッドレスモードで起動

    Returns:
        launched browser. 失敗したら fallback ブラウザを試す
    """
    launch_order = [prefer] + (["firefox"] if prefer == "chromium" else ["chromium"])
    last_err = None
    for name in launch_order:
        try:
            browser_type = getattr(playwright, name)
            args = ["--disable-blink-features=AutomationControlled"] if name == "chromium" else []
            return browser_type.launch(headless=headless, args=args, timeout=30000)
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("No browser available")
