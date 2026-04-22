/**
 * 買取価格コレクター — Service Worker
 * content.js からのメッセージを受け取り、タブ管理と自動巡回を行う
 */

// --- タブクローズ（安全な削除ヘルパー）---
// chrome.tabs.remove はタブが既に閉じられているとPromiseがrejectする。
// catch忘れで "Uncaught (in promise) Error: No tab with id: ..." が出ていたため
// 全ての remove 呼び出しで .catch を付ける。
function _safeRemoveTab(tabId) {
  try {
    const result = chrome.tabs.remove(tabId);
    if (result && typeof result.catch === "function") {
      result.catch(() => { /* already closed */ });
    }
  } catch (_) { /* already closed */ }
}

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message.action === "closeTab" && sender.tab) {
    const tabId = sender.tab.id;
    const delay = message.delay || 300;
    setTimeout(() => _safeRemoveTab(tabId), delay);
  }

  // 巡回モード: content.js から送信完了通知を受けたらこのタブの枠を解放
  if (message.action === "crawlNext" && sender.tab) {
    _finishTab(sender.tab.id);
  }
});

// --- 自動巡回機能 ---

const CRAWL_SITES = {
  "ビックカメラ": "https://www.biccamera.com/bc/category/?q={JAN}",
  "ケーズデンキ": "https://www.ksdenki.com/shop/e/search/?keyword={JAN}",
  "ジョーシン": "https://joshinweb.jp/servlet/emall/search?keyword={JAN}",
  "ノジマ": "https://online.nojima.co.jp/app/catalog/list/init?searchWord={JAN}",
  "エディオン": "https://www.edion.com/item_list.html?keyword={JAN}",
  "コジマ": "https://www.kojima.net/ec/disp/CSfDispListPage_001.jsp?keyword={JAN}",
  "auPAYマーケット": "https://wowma.jp/itemlist?e_scope=O&keyword={JAN}",
  "セブンネット": "https://7net.omni7.jp/search/?keyword={JAN}",
  "フジヤカメラ": "https://www.fujiya-camera.co.jp/shop/goods/search.aspx?keyword={JAN}",
  "楽天ブックス": "https://books.rakuten.co.jp/search?sitem={JAN}",
  // ソフマップは実ブラウザでもbot検知（「アクセス遮断」画面）されるため除外
};

const _CONCURRENCY = 2;       // 同時オープンタブ数上限（3→2: ブラウザ負荷削減）
const _TAB_TIMEOUT_MS = 35000; // タブ強制クローズまでの猶予（20s→35s: SPA対応）
let _crawlQueue = [];         // [{jan, url, site}]
let _crawlActive = false;
let _crawlDelay = 500;        // タブ起動のバースト回避用・最小間隔(ms)
let _activeTabs = new Map();  // tabId → { timeoutId, site, jan }

function _buildCrawlQueue(janList, sites) {
  const queue = [];
  for (const jan of janList) {
    for (const [site, tmpl] of Object.entries(CRAWL_SITES)) {
      if (sites && sites.length > 0 && !sites.includes(site)) continue;
      queue.push({ jan, url: tmpl.replace("{JAN}", jan), site });
    }
  }
  return queue;
}

function _openOneTab(next) {
  if (!_crawlActive) return;
  console.log(`[巡回] ${next.site} JAN=${next.jan} (残り${_crawlQueue.length}件, 並行${_activeTabs.size + 1}/${_CONCURRENCY})`);
  chrome.tabs.create({ url: next.url, active: false }, (tab) => {
    if (!tab) return;
    // セーフガード: 一定時間で crawlNext が来なければ強制クローズして枠解放
    const timeoutId = setTimeout(() => {
      console.log(`[巡回] タイムアウト: ${next.site} JAN=${next.jan} → 強制クローズ (${_TAB_TIMEOUT_MS/1000}s超)`);
      _safeRemoveTab(tab.id);
      _finishTab(tab.id);
    }, _TAB_TIMEOUT_MS);
    _activeTabs.set(tab.id, { timeoutId, site: next.site, jan: next.jan });
  });
}

function _openNextCrawlUrl() {
  if (!_crawlActive) return;

  // 空き枠を埋める。初期起動時は _CONCURRENCY 個をスタガで起動
  const toOpen = Math.min(_CONCURRENCY - _activeTabs.size, _crawlQueue.length);
  for (let i = 0; i < toOpen; i++) {
    const next = _crawlQueue.shift();
    if (i === 0) {
      _openOneTab(next);
    } else {
      setTimeout(() => _openOneTab(next), i * _crawlDelay);
    }
  }

  if (_activeTabs.size === 0 && _crawlQueue.length === 0) {
    _crawlActive = false;
    console.log("[巡回] 完了");
  }
}

function _finishTab(tabId) {
  const entry = _activeTabs.get(tabId);
  if (entry) {
    clearTimeout(entry.timeoutId);
    _activeTabs.delete(tabId);
  }
  _openNextCrawlUrl();
}

/**
 * 巡回を開始する
 * @param {string[]} janList - JANコードの配列
 * @param {string[]} sites - 対象サイト名の配列（空なら全サイト）
 * @param {number} delay - タブ起動間の最小間隔(ms)
 */
function startCrawl(janList, sites, delay) {
  if (_crawlActive) {
    console.log("[巡回] 既に実行中");
    return { status: "already_running", remaining: _crawlQueue.length };
  }

  _crawlDelay = delay || 500;
  _crawlQueue = _buildCrawlQueue(janList, sites);
  _crawlActive = true;

  console.log(`[巡回] 開始: ${janList.length}商品 × ${Object.keys(CRAWL_SITES).length}サイト = ${_crawlQueue.length}件 (並行${_CONCURRENCY})`);
  _openNextCrawlUrl();
  return { status: "started", total: _crawlQueue.length };
}

// 外部（price_server）からのメッセージで巡回開始
chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  if (message.action === "startCrawl") {
    const result = startCrawl(message.janList || [], message.sites || [], message.delay || 500);
    sendResponse(result);
  }
  if (message.action === "crawlStatus") {
    sendResponse({
      active: _crawlActive,
      remaining: _crawlQueue.length,
      active_tabs: _activeTabs.size,
    });
  }
  if (message.action === "stopCrawl") {
    _crawlQueue = [];
    _crawlActive = false;
    for (const entry of _activeTabs.values()) {
      clearTimeout(entry.timeoutId);
    }
    _activeTabs.clear();
    sendResponse({ status: "stopped" });
  }
});

// --- 自動ポーリング: price_server のクロールキューを監視 ---
// chrome.alarms を使用（Manifest V3 の Service Worker は setInterval だとスリープで停止する）

const POLL_URL = "http://127.0.0.1:8502/crawl_queue";
const ALARM_NAME = "pollCrawlQueue";

async function _pollCrawlQueue() {
  if (_crawlActive) return;

  try {
    // GETはpeek（覗くだけ、キューは消費しない）
    const resp = await fetch(POLL_URL);
    if (!resp.ok) return;

    const data = await resp.json();
    if (!data.janList || data.janList.length === 0) return;

    // キューを消費（DELETEでクリア）してから巡回開始
    await fetch(POLL_URL, { method: "DELETE" });

    console.log(`[自動巡回] キュー受信: ${data.janList.length}件`);
    startCrawl(data.janList, data.sites || [], 500);
  } catch (e) {
    // price_server未起動時はサイレントに無視
  }
}

// chrome.alarms で定期ポーリング（Service Workerスリープでも確実に発火）
chrome.alarms.create(ALARM_NAME, { periodInMinutes: 0.1 });  // 6秒間隔

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) {
    _pollCrawlQueue();
  }
});

// Service Worker 起動時にも即チェック
_pollCrawlQueue();
