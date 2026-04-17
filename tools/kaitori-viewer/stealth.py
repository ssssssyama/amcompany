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
