/**
 * 買取価格コレクター — Service Worker
 * content.js からのメッセージを受け取り、タブ管理と自動巡回を行う
 */

// --- タブクローズ ---
chrome.runtime.onMessage.addListener((message, sender) => {
  if (message.action === "closeTab" && sender.tab) {
    const tabId = sender.tab.id;
    const delay = message.delay || 2000;
    setTimeout(() => {
      chrome.tabs.remove(tabId);
    }, delay);
  }

  // 巡回モード: content.js から送信完了通知を受けたら次のURLを開く
  if (message.action === "crawlNext") {
    _openNextCrawlUrl();
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
  // ソフマップは実ブラウザでもbot検知（「アクセス遮断」画面）されるため除外
};

let _crawlQueue = [];  // [{jan, url, site}]
let _crawlActive = false;
let _crawlDelay = 4000;  // タブ間の待機時間(ms)
let _crawlTabId = null;

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

let _crawlTimeout = null;  // タイムアウト強制クローズ用

function _openNextCrawlUrl() {
  // 前回のタイムアウトをクリア
  if (_crawlTimeout) {
    clearTimeout(_crawlTimeout);
    _crawlTimeout = null;
  }

  if (_crawlQueue.length === 0) {
    _crawlActive = false;
    _crawlTabId = null;
    console.log("[巡回] 完了");
    return;
  }

  const next = _crawlQueue.shift();
  console.log(`[巡回] ${next.site} JAN=${next.jan} (残り${_crawlQueue.length}件)`);

  setTimeout(() => {
    chrome.tabs.create({ url: next.url, active: false }, (tab) => {
      _crawlTabId = tab.id;

      // セーフガード: 25秒経っても crawlNext が来なければ強制クローズして次へ
      // （SPA対策: JS描画15秒 + content.js処理5秒 + バッファ5秒）
      _crawlTimeout = setTimeout(() => {
        console.log(`[巡回] タイムアウト: ${next.site} JAN=${next.jan} → 強制クローズ`);
        try {
          chrome.tabs.remove(tab.id);
        } catch (e) { /* already closed */ }
        _openNextCrawlUrl();
      }, 25000);
    });
  }, _crawlDelay);
}

/**
 * 巡回を開始する
 * @param {string[]} janList - JANコードの配列
 * @param {string[]} sites - 対象サイト名の配列（空なら全サイト）
 * @param {number} delay - タブ間待機(ms)
 */
function startCrawl(janList, sites, delay) {
  if (_crawlActive) {
    console.log("[巡回] 既に実行中");
    return { status: "already_running", remaining: _crawlQueue.length };
  }

  _crawlDelay = delay || 4000;
  _crawlQueue = _buildCrawlQueue(janList, sites);
  _crawlActive = true;

  console.log(`[巡回] 開始: ${janList.length}商品 × ${Object.keys(CRAWL_SITES).length}サイト = ${_crawlQueue.length}件`);
  _openNextCrawlUrl();
  return { status: "started", total: _crawlQueue.length };
}

// 外部（price_server）からのメッセージで巡回開始
chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  if (message.action === "startCrawl") {
    const result = startCrawl(message.janList || [], message.sites || [], message.delay || 4000);
    sendResponse(result);
  }
  if (message.action === "crawlStatus") {
    sendResponse({
      active: _crawlActive,
      remaining: _crawlQueue.length,
    });
  }
  if (message.action === "stopCrawl") {
    _crawlQueue = [];
    _crawlActive = false;
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
    startCrawl(data.janList, data.sites || [], 4000);
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
