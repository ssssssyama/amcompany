/**
 * 買取価格コレクター — Content Script v1.2
 * 量販店ECサイトから商品価格を自動抽出し、ローカルサーバーに送信する
 */

// 二重実行防止
if (window.__kaitoriCollectorLoaded) {
  // already running
} else {
  window.__kaitoriCollectorLoaded = true;

const API_URL = "http://127.0.0.1:8502/add_price";

// --- JAN検証 ---

function isValidJAN(code) {
  // 13桁JANのチェックディジット検証
  if (code.length === 13) {
    let sum = 0;
    for (let i = 0; i < 12; i++) {
      sum += parseInt(code[i], 10) * (i % 2 === 0 ? 1 : 3);
    }
    const check = (10 - (sum % 10)) % 10;
    return check === parseInt(code[12], 10);
  }
  // 8桁JANのチェックディジット検証
  if (code.length === 8) {
    let sum = 0;
    for (let i = 0; i < 7; i++) {
      sum += parseInt(code[i], 10) * (i % 2 === 0 ? 3 : 1);
    }
    const check = (10 - (sum % 10)) % 10;
    return check === parseInt(code[7], 10);
  }
  return false;
}

// URLからJANコードを抽出
function extractJAN() {
  const url = new URL(window.location.href);
  // クエリパラメータから探す
  for (const key of ["q", "keyword", "searchWord", "word", "KWD", "s", "k"]) {
    const val = url.searchParams.get(key);
    if (val && /^(?:\d{8}|\d{13})$/.test(val.trim()) && isValidJAN(val.trim())) {
      return val.trim();
    }
  }
  // URLパス内の数字列（チェックディジット検証付き）
  const pathMatches = url.pathname.match(/\d{8}(?!\d)|\d{13}(?!\d)/g);
  if (pathMatches) {
    for (const m of pathMatches) {
      if (isValidJAN(m)) return m;
    }
  }
  // ページ内のJANコード表示
  const body = document.body.innerText;
  const janMatch = body.match(/(?:JAN|EAN|バーコード)[：:\s]*(\d{13})/i);
  if (janMatch && isValidJAN(janMatch[1])) return janMatch[1];
  return null;
}

// --- サイト別の価格抽出ルール ---

const SITE_RULES = {
  "biccamera.com": {
    source: "ビックカメラ",
    priceSelectors: [
      ".bcs_price .val",
      ".product_price .val",
      ".itemPrice .val",
    ],
    extractPrice: () => {
      for (const sel of [".bcs_price .val", ".product_price .val", ".itemPrice .val", "[class*='price']"]) {
        const el = document.querySelector(sel);
        if (el) {
          const p = parsePrice(el.textContent);
          if (p > 0) return p;
        }
      }
      const text = document.body.innerText;
      const yenM = text.match(/[￥¥](\d{1,3}(?:,\d{3}){1,2})/);
      if (yenM) {
        const p = parseInt(yenM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      const enM = text.match(/([\d,]+)\s*円\s*[（(]税込/);
      if (enM) {
        const p = parseInt(enM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      return 0;
    },
  },
  "kojima.net": {
    source: "コジマ",
    priceSelectors: [
      ".productPrice",
      ".price .num",
      ".sellingPrice",
      ".sale_price",
      ".bcs_price .val",
    ],
    // コジマは「27,800 円(税込)」形式（￥なし）のためカスタム抽出
    extractPrice: () => {
      // まずセレクタを試行
      for (const sel of [".productPrice", ".price .num", ".sellingPrice", ".sale_price", ".bcs_price .val"]) {
        const el = document.querySelector(sel);
        if (el) {
          const p = parsePrice(el.textContent);
          if (p > 0) return p;
        }
      }
      // フォールバック: 「数字 円(税込)」パターン
      const text = document.body.innerText;
      const matches = text.match(/([\d,]+)\s*円\s*[（(]税込/g);
      if (matches) {
        const prices = matches
          .map((m) => parseInt(m.replace(/[,円\s（(税込)]/g, ""), 10))
          .filter((p) => p >= 1000 && p <= 10000000);
        if (prices.length > 0) return Math.min(...prices);
      }
      return extractGenericPrice();
    },
  },
  "sofmap.com": {
    source: "ソフマップ",
    priceSelectors: [
      ".product_price",
      ".salesPrice",
    ],
    extractPrice: () => {
      for (const sel of [".product_price", ".salesPrice", "[class*='price']"]) {
        const el = document.querySelector(sel);
        if (el) {
          const p = parsePrice(el.textContent);
          if (p > 0) return p;
        }
      }
      const text = document.body.innerText;
      const yenM = text.match(/[￥¥](\d{1,3}(?:,\d{3}){1,2})/);
      if (yenM) {
        const p = parseInt(yenM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      const enM = text.match(/([\d,]+)\s*円\s*[（(]税込/);
      if (enM) {
        const p = parseInt(enM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      return 0;
    },
  },
  "ksdenki.com": {
    source: "ケーズデンキ",
    priceSelectors: [
      ".goods_price .price",
      ".goods_price",
      ".itemPrice",
      ".product-price",
      ".price-area",
    ],
    // ケーズデンキはSPAで遅延レンダリング + ￥なし「円(税込)」の場合がある
    extractPrice: () => {
      for (const sel of [".goods_price .price", ".goods_price", ".itemPrice",
                          ".product-price", ".price-area",
                          "[class*='price']"]) {
        const el = document.querySelector(sel);
        if (el) {
          const p = parsePrice(el.textContent);
          if (p > 0) return p;
        }
      }
      const text = document.body.innerText;
      // ￥パターン
      const yenM = text.match(/[￥¥](\d{1,3}(?:,\d{3}){1,2})/);
      if (yenM) {
        const p = parseInt(yenM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      // 円(税込) パターン
      const enM = text.match(/([\d,]+)\s*円\s*[（(]税込/);
      if (enM) {
        const p = parseInt(enM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      return 0;
    },
  },
  "joshinweb.jp": {
    source: "ジョーシン",
    priceSelectors: [
      ".priceArea .price",
      ".sellingPrice",
      ".productPrice",
      ".price-num",
    ],
    extractPrice: () => {
      for (const sel of [".priceArea .price", ".sellingPrice", ".productPrice",
                          ".price-num", "[class*='price']"]) {
        const el = document.querySelector(sel);
        if (el) {
          const p = parsePrice(el.textContent);
          if (p > 0) return p;
        }
      }
      const text = document.body.innerText;
      // ￥パターン
      const yenM = text.match(/[￥¥](\d{1,3}(?:,\d{3}){1,2})/);
      if (yenM) {
        const p = parseInt(yenM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      // 円(税込) パターン
      const enM = text.match(/([\d,]+)\s*円\s*[（(]税込/);
      if (enM) {
        const p = parseInt(enM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      return 0;
    },
  },
  "nojima.co.jp": {
    source: "ノジマ",
    priceSelectors: [
      ".productPrice",
      ".itemPrice .num",
      ".price",
    ],
    extractPrice: () => {
      for (const sel of [".productPrice", ".itemPrice .num", ".price", "[class*='price']"]) {
        const el = document.querySelector(sel);
        if (el) {
          const p = parsePrice(el.textContent);
          if (p > 0) return p;
        }
      }
      const text = document.body.innerText;
      const yenM = text.match(/[￥¥](\d{1,3}(?:,\d{3}){1,2})/);
      if (yenM) {
        const p = parseInt(yenM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      const enM = text.match(/([\d,]+)\s*円\s*[（(]税込/);
      if (enM) {
        const p = parseInt(enM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      return 0;
    },
  },
  "edion.com": {
    source: "エディオン",
    priceSelectors: [
      ".productPrice",
      ".itemPrice .num",
      ".price",
    ],
    extractPrice: () => {
      for (const sel of [".productPrice", ".itemPrice .num", ".price", "[class*='price']"]) {
        const el = document.querySelector(sel);
        if (el) {
          const p = parsePrice(el.textContent);
          if (p > 0) return p;
        }
      }
      const text = document.body.innerText;
      const yenM = text.match(/[￥¥](\d{1,3}(?:,\d{3}){1,2})/);
      if (yenM) {
        const p = parseInt(yenM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      const enM = text.match(/([\d,]+)\s*円\s*[（(]税込/);
      if (enM) {
        const p = parseInt(enM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      return 0;
    },
  },
  "yodobashi.com": {
    source: "ヨドバシ",
    priceSelectors: [],
    extractPrice: () => {
      // ヨドバシ固有: 販売価格は￥マーク付き、ポイントも￥付きのため厳密に区別
      // 商品詳細ページの販売価格セレクタ
      const priceArea = document.querySelector("#js_scl_priceBox, .pInfo .red, .productPrice");
      if (priceArea) {
        // ポイント表記の前の￥数値を販売価格とする
        const priceText = priceArea.textContent;
        const pointValues = new Set();
        for (const pm of priceText.matchAll(/[￥¥]([\d,]+)\s*(?:ポイント|円相当)/g)) {
          pointValues.add(pm[1]);
        }
        for (const pm of priceText.matchAll(/[￥¥]([\d,]+)/g)) {
          if (!pointValues.has(pm[1])) {
            const p = parseInt(pm[1].replace(/,/g, ""), 10);
            if (p >= 1000) return p;
          }
        }
      }
      // ページ全体からポイント除外で取得
      const text = document.body.innerText;
      const pointVals = new Set();
      for (const pm of text.matchAll(/[￥¥]([\d,]+)\s*(?:ポイント|円相当)/g)) {
        pointVals.add(pm[1]);
      }
      for (const pm of text.matchAll(/[￥¥](\d{1,3}(?:,\d{3}){1,2})/g)) {
        if (!pointVals.has(pm[1])) {
          const p = parseInt(pm[1].replace(/,/g, ""), 10);
          if (p >= 1000) return p;
        }
      }
      // 円(税込) フォールバック
      const enM = text.match(/([\d,]+)\s*円\s*[（(]税込/);
      if (enM) {
        const p = parseInt(enM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      return 0;
    },
  },
  "amazon.co.jp": {
    source: "Amazon",
    priceSelectors: [
      ".a-price .a-offscreen",
      "#priceblock_ourprice",
      "#priceblock_dealprice",
      "#corePrice_feature_div .a-offscreen",
    ],
    extractName: () => {
      const el = document.querySelector("#productTitle, h1 span");
      return el ? el.textContent.trim() : extractGenericName();
    },
    extractPrice: () => {
      // Amazonの価格セレクタを試行
      for (const sel of [".a-price:not([data-a-strike]) .a-offscreen",
                          "#corePrice_feature_div .a-offscreen",
                          "#priceblock_ourprice", "#priceblock_dealprice"]) {
        const el = document.querySelector(sel);
        if (el) {
          const p = parsePrice(el.textContent);
          if (p > 0) return p;
        }
      }
      // ￥パターン（中古品セクションより前）
      const text = document.body.innerText;
      const beforeUsed = text.split("中古品")[0] || text;
      const yenM = beforeUsed.match(/[￥¥](\d{1,3}(?:,\d{3}){1,2})/);
      if (yenM) {
        const p = parseInt(yenM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      // 円(税込) フォールバック
      const enM = text.match(/([\d,]+)\s*円\s*[（(]税込/);
      if (enM) {
        const p = parseInt(enM[1].replace(/,/g, ""), 10);
        if (p >= 1000) return p;
      }
      return extractGenericPrice();
    },
  },
};

// --- 共通ユーティリティ ---

function parsePrice(text) {
  const cleaned = text.replace(/[￥¥,\s税込税抜円]/g, "");
  const num = parseInt(cleaned, 10);
  return isNaN(num) || num < 100 ? 0 : num;
}

function extractGenericPrice() {
  const text = document.body.innerText;
  // パターン1: ￥ マーク付き（ヨドバシ、Amazon等）
  const yenMatches = text.match(/[￥¥]\s*([\d,]+)/g);
  // パターン2: 「円(税込)」表記（コジマ、一部EC）
  const enMatches = text.match(/([\d,]+)\s*円\s*[（(]税込/g);

  const prices = [];
  if (yenMatches) {
    for (const m of yenMatches) {
      const p = parseInt(m.replace(/[￥¥\s,]/g, ""), 10);
      if (p >= 1000 && p <= 10000000) prices.push(p);
    }
  }
  if (enMatches) {
    for (const m of enMatches) {
      const p = parseInt(m.replace(/[,円\s（(税込)]/g, ""), 10);
      if (p >= 1000 && p <= 10000000) prices.push(p);
    }
  }
  return prices.length > 0 ? Math.min(...prices) : 0;
}

function extractGenericName() {
  const el = document.querySelector(
    "h1, [class*='productName'], [class*='product_name'], title"
  );
  return el ? el.textContent.trim().substring(0, 100) : "";
}

function extractPriceBySelectors(selectors) {
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) {
      const p = parsePrice(el.textContent);
      if (p > 0) return p;
    }
  }
  return 0;
}

function getRule() {
  const host = window.location.hostname;
  for (const [domain, rule] of Object.entries(SITE_RULES)) {
    if (host.includes(domain)) return rule;
  }
  return null;
}

// --- MutationObserver: 価格要素の出現を待つ ---

function waitForPrice(rule, timeoutMs = 10000) {
  return new Promise((resolve) => {
    // まず即座にチェック
    const immediate = getPriceFromRule(rule);
    if (immediate > 0) {
      resolve(immediate);
      return;
    }

    let resolved = false;
    const timer = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        observer.disconnect();
        // タイムアウト時に最終チェック
        resolve(getPriceFromRule(rule));
      }
    }, timeoutMs);

    const observer = new MutationObserver(() => {
      if (resolved) return;
      const price = getPriceFromRule(rule);
      if (price > 0) {
        resolved = true;
        observer.disconnect();
        clearTimeout(timer);
        resolve(price);
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  });
}

function getPriceFromRule(rule) {
  if (rule.extractPrice) return rule.extractPrice();
  if (rule.priceSelectors && rule.priceSelectors.length > 0) {
    const p = extractPriceBySelectors(rule.priceSelectors);
    if (p > 0) return p;
  }
  return extractGenericPrice();
}

// --- バッジ表示 ---

function showBadge(text, color = "#1a73e8") {
  const badge = document.createElement("div");
  badge.textContent = text;
  badge.style.cssText =
    `position:fixed;top:10px;right:10px;z-index:999999;padding:10px 16px;` +
    `background:${color};color:#fff;border-radius:8px;font-size:14px;` +
    `box-shadow:0 2px 8px rgba(0,0,0,0.3);font-family:sans-serif;` +
    `transition:opacity 0.3s;`;
  document.body.appendChild(badge);
  setTimeout(() => {
    badge.style.opacity = "0";
    setTimeout(() => badge.remove(), 300);
  }, 4000);
}

// --- 設定取得 ---

async function getAutoCloseSetting() {
  return new Promise((resolve) => {
    try {
      chrome.storage.local.get({ autoClose: true }, (data) => {
        resolve(data.autoClose);
      });
    } catch {
      resolve(true); // デフォルトON
    }
  });
}

// --- DOM構造デバッグ送信 ---

async function sendDebugDom(rule) {
  try {
    const body = document.body;
    const text = body ? body.innerText : "";

    // 価格セレクタの試行結果
    const selectorResults = {};
    if (rule && rule.priceSelectors) {
      for (const sel of rule.priceSelectors) {
        const el = document.querySelector(sel);
        selectorResults[sel] = el ? el.textContent.trim().substring(0, 100) : null;
      }
    }

    // 汎用価格候補
    const yenMatches = text.match(/[￥¥]\s*[\d,]+/g) || [];
    const enMatches = text.match(/[\d,]+\s*円/g) || [];

    // price/Price を含むclass属性を持つ要素
    const priceEls = document.querySelectorAll("[class*='price'], [class*='Price']");
    const priceElements = [];
    priceEls.forEach((el) => {
      priceElements.push({
        tag: el.tagName,
        class: el.className.substring(0, 80),
        text: el.textContent.trim().substring(0, 80),
      });
    });

    await fetch("http://127.0.0.1:8502/debug_dom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: rule ? rule.source : "unknown",
        url: window.location.href,
        priceSelectors: selectorResults,
        genericPrice: { yen: yenMatches.slice(0, 5), en: enMatches.slice(0, 5) },
        priceElements: priceElements.slice(0, 10),
        bodySnippet: text.substring(0, 500),
      }),
    });
  } catch (e) {
    console.log("[買取コレクター] デバッグ送信失敗:", e.message);
  }
}

// --- メイン処理 ---

async function main() {
  // 巡回継続+タブクローズを確実に行うヘルパー
  function finishAndClose(delay) {
    chrome.runtime.sendMessage({ action: "crawlNext" });
    getAutoCloseSetting().then((auto) => {
      if (auto) {
        chrome.runtime.sendMessage({ action: "closeTab", delay: delay || 2000 });
      }
    });
  }

  // 初期待機（DOM安定のため最低1秒）
  await new Promise((r) => setTimeout(r, 1000));

  const rule = getRule();
  if (!rule) {
    // マッチするサイトルールがない（対象外ページ）
    finishAndClose(1000);
    return;
  }

  const jan = extractJAN();
  if (!jan) {
    console.log("[買取コレクター] JANコード検出できず:", window.location.href);
    finishAndClose(1500);
    return;
  }

  // MutationObserverで価格要素の出現を待つ（最大10秒）
  // SPA対策: ケーズデンキ等はJSレンダリングに時間がかかるため15秒待つ
  const price = await waitForPrice(rule, 15000);
  if (price <= 0) {
    console.log("[買取コレクター] 価格検出できず:", jan, window.location.href);
    showBadge(`価格検出できず: ${jan}`, "#f44336");
    // DOM構造をサーバーに送信して原因分析
    await sendDebugDom(rule);
    finishAndClose(2000);
    return;
  }

  const name = rule.extractName ? rule.extractName() : extractGenericName();

  const data = {
    jan: jan,
    price: price,
    name: name,
    shop: rule.source,
    source: rule.source,
    url: window.location.href,
  };

  console.log("[買取コレクター] 送信:", data);

  try {
    const resp = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    const result = await resp.json();
    console.log("[買取コレクター] 結果:", result);

    if (result.action === "added") {
      const profit = result["現金利益"];
      const profitStr = profit != null ? profit.toLocaleString() : "?";
      showBadge(
        `${rule.source} ${price.toLocaleString()}円 → 利益${profitStr}円`,
        profit > 0 ? "#2e7d32" : "#f44336"
      );
      finishAndClose(3000);
    } else if (result.action === "skipped") {
      const reason = result.reason || "";
      let msg = `${rule.source} スキップ`;
      if (reason === "excluded product") {
        msg += "（除外対象）";
      } else if (reason === "existing price is lower") {
        msg += "（既存価格のほうが安い）";
      }
      showBadge(msg, "#ff9800");
      finishAndClose(2000);
    } else if (result.error) {
      showBadge(`エラー: ${result.error.substring(0, 50)}`, "#f44336");
      finishAndClose(2000);
    } else {
      // 予期しないレスポンス
      finishAndClose(2000);
    }
  } catch (e) {
    console.log("[買取コレクター] サーバー未起動またはエラー:", e.message);
    showBadge("サーバー未起動", "#f44336");
    finishAndClose(2000);
  }
}

main();

} // end of double-execution guard
