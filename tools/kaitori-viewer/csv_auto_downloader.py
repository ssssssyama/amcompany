"""買取スキャナー（hikaku-342505.firebaseapp.com）の全データCSV自動ダウンロード

storage_state方式（Cookie+localStorageのJSON保存）でGoogle認証を保持する。
Windowsの --remote-debugging-pipe 不安定問題を回避するため、
launch_persistent_context ではなく launch() + storage_state を使用。

- 初回実行（--headed）: 通常のブラウザで手動Googleログイン → 認証状態をJSON保存
- 2回目以降: JSON読み込みで即認証済み状態、headless で全自動
- 認証切れ時: ヘッドレス失敗を検知し、ヘッドフル再試行

使い方:
    python csv_auto_downloader.py            # 既定: ヘッドレス試行→失敗ならヘッドフル
    python csv_auto_downloader.py --headed   # 強制ヘッドフル（初回ログイン用）
    python csv_auto_downloader.py --reset    # 保存された認証情報をクリア

出力:
    c:/Users/amayo/amcompany/all_data_YYYYMMDDHHMM.csv
"""

import argparse
import json
import logging
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

SITE_URL = "https://hikaku-342505.firebaseapp.com/"
CSV_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent  # c:/Users/amayo/amcompany
STATE_FILE = Path.home() / ".kaitori-viewer" / "hikaku_auth_state.json"
# ダウンロードされたCSVの判定パターン
CSV_FILENAME_PATTERN = re.compile(r"(?:all_data|買取|kaitori|hikaku).*\.csv$", re.IGNORECASE)


def _find_csv_button(page):
    """「全データcsv保存」またはそれに相当するボタンを探す"""
    # テキストベース検索（Vuetifyのv-btn対策）
    candidates = page.evaluate("""
    () => {
        const targets = ['全データcsv保存', '全データCSV保存', '全データCSVを保存',
                         'CSV保存', 'CSVダウンロード', 'CSV出力', '全データCSV'];
        const all = document.querySelectorAll('button, a, [role=button], .v-btn, .v-list-item');
        for (const el of all) {
            const text = (el.innerText || el.textContent || '').trim();
            for (const t of targets) {
                if (text.includes(t)) {
                    return {
                        found: true,
                        text: text.slice(0, 100),
                        selector: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
                    };
                }
            }
        }
        return {found: false};
    }
    """)
    return candidates


def _click_csv_button(page) -> bool:
    """CSVボタンをクリックする"""
    # JSで直接クリック（Vuetifyの内部要素対策）
    clicked = page.evaluate("""
    () => {
        const targets = ['全データcsv保存', '全データCSV保存', '全データCSVを保存',
                         'CSV保存', 'CSVダウンロード', 'CSV出力', '全データCSV'];
        const all = document.querySelectorAll('button, a, [role=button], .v-btn, .v-list-item');
        for (const el of all) {
            const text = (el.innerText || el.textContent || '').trim();
            for (const t of targets) {
                if (text.includes(t)) {
                    el.click();
                    return true;
                }
            }
        }
        return false;
    }
    """)
    return bool(clicked)


def _is_logged_in(page) -> bool:
    """ログイン済みかを判定。「ログインして始める」が消え、マイページ等が見えていれば OK"""
    info = page.evaluate("""
    () => {
        const body = (document.body?.innerText || '');
        return {
            hasLoginButton: body.includes('ログインして始める'),
            hasLogout: body.includes('ログアウト'),
            hasMypage: body.includes('マイページ'),
            hasCsvButton: body.includes('CSV保存') || body.includes('全データCSV') || body.includes('全データcsv'),
        };
    }
    """)
    # CSVボタンが見えていれば確実にログイン済み
    if info.get("hasCsvButton"):
        return True
    # ログアウトボタンがあればログイン済み（「ログインして始める」が残ってるのは SPA の初期表示）
    return bool(info.get("hasLogout"))


IDB_FILE = Path.home() / ".kaitori-viewer" / "hikaku_idb.json"

# Firebase認証は IndexedDB（firebaseLocalStorageDb）にトークンを保持するため、
# Cookie+localStorageだけを保存するstorage_stateでは認証が持続しない。
# IndexedDB全体をJSONにダンプ/リストアする補助機能を提供する。

_IDB_EXPORT_JS = """
async () => {
  const result = {};
  let dbs;
  try { dbs = await indexedDB.databases(); }
  catch { return result; }
  for (const info of dbs) {
    if (!info.name) continue;
    try {
      const db = await new Promise((res, rej) => {
        const req = indexedDB.open(info.name);
        req.onsuccess = () => res(req.result);
        req.onerror = () => rej(req.error);
      });
      const storeNames = Array.from(db.objectStoreNames);
      const dbData = {_version: db.version, _stores: {}};
      for (const s of storeNames) {
        const tx = db.transaction(s, 'readonly');
        const store = tx.objectStore(s);
        const keysReq = store.getAllKeys();
        const valsReq = store.getAll();
        const keys = await new Promise(r => { keysReq.onsuccess = () => r(keysReq.result); });
        const vals = await new Promise(r => { valsReq.onsuccess = () => r(valsReq.result); });
        dbData._stores[s] = keys.map((k, i) => ({key: k, value: vals[i]}));
      }
      db.close();
      result[info.name] = dbData;
    } catch (e) { /* skip */ }
  }
  return result;
}
"""

_IDB_IMPORT_JS = """
async (data) => {
  for (const [dbName, info] of Object.entries(data)) {
    try {
      // 既存DBを削除して再構築（onupgradeneededで同じstore構造を作るのは難しいため）
      await new Promise(res => {
        const req = indexedDB.deleteDatabase(dbName);
        req.onsuccess = () => res();
        req.onerror = () => res();
        req.onblocked = () => res();
      });
      const db = await new Promise((resolve, reject) => {
        const req = indexedDB.open(dbName, info._version || 1);
        req.onupgradeneeded = (e) => {
          const d = e.target.result;
          for (const s of Object.keys(info._stores || {})) {
            if (!d.objectStoreNames.contains(s)) {
              d.createObjectStore(s);
            }
          }
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
      for (const [storeName, entries] of Object.entries(info._stores || {})) {
        if (!db.objectStoreNames.contains(storeName)) continue;
        const tx = db.transaction(storeName, 'readwrite');
        const store = tx.objectStore(storeName);
        for (const e of entries) {
          try { store.put(e.value, e.key); }
          catch { try { store.put(e.value); } catch {} }
        }
        await new Promise(r => { tx.oncomplete = r; tx.onerror = r; });
      }
      db.close();
    } catch (e) { /* skip */ }
  }
}
"""


def _save_auth_state(context, page=None) -> None:
    """Cookie+localStorage+IndexedDBを保存"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(STATE_FILE))
    logger.info("認証情報を保存: %s", STATE_FILE)
    # IndexedDB（Firebase認証トークン）も保存
    if page is not None:
        try:
            idb_data = page.evaluate(_IDB_EXPORT_JS)
            IDB_FILE.write_text(json.dumps(idb_data, ensure_ascii=False, default=str),
                                encoding="utf-8")
            logger.info("IndexedDBを保存: %s (%d DB)", IDB_FILE, len(idb_data))
        except Exception as e:
            logger.warning("IndexedDB保存失敗: %s", e)


def _restore_indexeddb(page) -> bool:
    """保存済みIndexedDBをリストア（サイトドメインで一度読み込んだ後に呼ぶ）"""
    if not IDB_FILE.exists():
        return False
    try:
        data = json.loads(IDB_FILE.read_text(encoding="utf-8"))
        page.evaluate(_IDB_IMPORT_JS, data)
        logger.info("IndexedDBをリストア: %d DB", len(data))
        return True
    except Exception as e:
        logger.warning("IndexedDBリストア失敗: %s", e)
        return False


def _load_auth_state() -> dict | None:
    """保存された認証情報を読み込む"""
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def download_csv(headless: bool = True, login_wait_sec: int = 180) -> Path | None:
    """CSVをダウンロードして保存先パスを返す（失敗時 None）

    Args:
        headless: ヘッドレスで起動するか（初回ログインは False 推奨）
        login_wait_sec: 手動ログイン待機の最大秒数（ヘッドフル時のみ）
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx_kwargs = {
            "accept_downloads": True,
            "viewport": {"width": 1280, "height": 900},
            "locale": "ja-JP",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        # 既存の認証情報をロード
        if STATE_FILE.exists():
            ctx_kwargs["storage_state"] = str(STATE_FILE)
            logger.info("認証情報をロード: %s", STATE_FILE)
        else:
            logger.info("認証情報なし（初回実行）")

        context = browser.new_context(**ctx_kwargs)

        try:
            page = context.new_page()
            logger.info("サイト訪問: %s", SITE_URL)
            page.goto(SITE_URL, wait_until="domcontentloaded", timeout=30000)
            # IndexedDB（Firebase認証トークン）をリストアしてからリロード
            if IDB_FILE.exists():
                if _restore_indexeddb(page):
                    logger.info("IndexedDBリストア完了、ページを再読み込み")
                    page.reload(wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3500)

            # ログイン状態確認
            if not _is_logged_in(page):
                if headless:
                    logger.error(
                        "未ログインで headless 実行できません。"
                        "初回は --headed で起動して手動ログインしてください"
                    )
                    return None
                logger.info("未ログイン検出。ブラウザ上でGoogleログインしてください")
                logger.info("（最大 %d 秒待機、ログイン完了を自動検知）", login_wait_sec)
                deadline = time.time() + login_wait_sec
                while time.time() < deadline:
                    time.sleep(3)
                    try:
                        if _is_logged_in(page):
                            logger.info("ログイン完了を検知しました")
                            break
                    except Exception:
                        continue
                else:
                    logger.error("ログインタイムアウト")
                    return None
                # ログイン成功直後に認証情報を保存（page経由でIndexedDBも）
                _save_auth_state(context, page)

            # CSVボタン検出
            page.wait_for_timeout(2000)
            found = _find_csv_button(page)
            if not found.get("found"):
                logger.warning("CSVボタンが見つかりません。メニューを開いて再試行")
                try:
                    page.click("button.v-app-bar__nav-icon", timeout=3000)
                    page.wait_for_timeout(1500)
                    found = _find_csv_button(page)
                except Exception:
                    pass

            if not found.get("found"):
                logger.error("CSVボタンが見つかりません。UI変更の可能性")
                return None
            logger.info("CSVボタン検出: %s", found.get("text", ""))

            # ダウンロード待ち受け + クリック
            # Firebase Hostingの一部アプリは blob: URL でダウンロードするため、
            # expect_download で検知できないケースがある。その場合はクリック後の
            # ページ遷移・ダイアログ表示をチェックして次ボタンを探す。
            download = None
            try:
                with page.expect_download(timeout=15000) as download_info:
                    if not _click_csv_button(page):
                        logger.error("CSVボタンクリックに失敗")
                        return None
                download = download_info.value
            except Exception:
                logger.info("1回目クリックではダウンロード発生せず、次画面を確認")

            # クリック後に「保存」「ダウンロード」系ボタンが現れた場合、2段階目を実行
            if not download:
                page.wait_for_timeout(2500)
                # 現在表示されている追加ボタンを調査
                extra_buttons = page.evaluate("""
                () => {
                    const targets = ['保存', 'ダウンロード', 'download', 'CSV出力', 'エクスポート', '出力'];
                    const all = document.querySelectorAll('button, a[role=button], [role=button], .v-btn');
                    const results = [];
                    for (const el of all) {
                        const text = (el.innerText || el.textContent || '').trim();
                        if (!text) continue;
                        for (const t of targets) {
                            if (text.includes(t)) {
                                results.push({text: text.slice(0, 80)});
                                break;
                            }
                        }
                    }
                    return results.slice(0, 10);
                }
                """)
                if extra_buttons:
                    logger.info("2段階目のボタン候補: %s", [b["text"][:40] for b in extra_buttons])
                    try:
                        with page.expect_download(timeout=30000) as download_info:
                            clicked = page.evaluate("""
                            () => {
                                const targets = ['保存', 'ダウンロード', 'download', 'CSV出力', 'エクスポート', '出力'];
                                const all = document.querySelectorAll('button, a[role=button], [role=button], .v-btn');
                                for (const el of all) {
                                    const text = (el.innerText || el.textContent || '').trim();
                                    for (const t of targets) {
                                        if (text.includes(t)) {
                                            el.click();
                                            return true;
                                        }
                                    }
                                }
                                return false;
                            }
                            """)
                            if not clicked:
                                return None
                        download = download_info.value
                    except Exception as e:
                        logger.error("2段階クリックでもダウンロード発生せず: %s", e)

            if not download:
                # 最終手段: ページ上の current URL とタイトルを記録
                try:
                    logger.error("最終状態 URL=%s / title=%s", page.url, page.title())
                    # スクリーンショット（手動確認用）
                    ss_path = Path.home() / ".kaitori-viewer" / "csv_download_fail.png"
                    page.screenshot(path=str(ss_path), full_page=True)
                    logger.error("スクリーンショット: %s", ss_path)
                except Exception:
                    pass
                return None

            # 保存
            ts = datetime.now().strftime("%Y%m%d%H%M")
            dest = CSV_OUTPUT_DIR / f"all_data_{ts}.csv"
            tmp_path = download.path()
            if tmp_path:
                shutil.copy(str(tmp_path), str(dest))
            else:
                download.save_as(str(dest))

            if dest.exists() and dest.stat().st_size > 1024:
                logger.info("保存完了: %s (%.2f MB)", dest, dest.stat().st_size / 1024 / 1024)
                # 成功時にも認証情報を更新（トークンリフレッシュ対応）
                try:
                    _save_auth_state(context, page)
                except Exception:
                    pass
                return dest
            logger.error("保存失敗またはファイルサイズ不足: %s", dest)
            return None

        finally:
            context.close()
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="買取スキャナーCSV自動ダウンロード")
    parser.add_argument("--headed", action="store_true",
                        help="ヘッドフル起動（初回ログイン用）")
    parser.add_argument("--show", action="store_true",
                        help="操作確認用にヘッドフル + 長めの待機")
    parser.add_argument("--login-wait", type=int, default=180,
                        help="手動ログイン待機秒数（デフォルト180）")
    parser.add_argument("--reset", action="store_true",
                        help="保存された認証情報をクリア")
    args = parser.parse_args()

    if args.reset:
        cleared = []
        for f in (STATE_FILE, IDB_FILE):
            if f.exists():
                f.unlink()
                cleared.append(str(f))
        if cleared:
            print("認証情報をクリアしました:")
            for c in cleared:
                print(f"  - {c}")
        else:
            print("認証情報はまだ保存されていません")
        sys.exit(0)

    # まずヘッドレスで試し、失敗したらヘッドフルにフォールバック
    headless = not (args.headed or args.show)
    result = download_csv(headless=headless, login_wait_sec=args.login_wait)

    if not result and headless:
        logger.warning("ヘッドレスで失敗。ヘッドフルで再試行します")
        result = download_csv(headless=False, login_wait_sec=args.login_wait)

    if result:
        print(f"CSV保存完了: {result}")
        sys.exit(0)
    else:
        print("CSV取得失敗")
        sys.exit(1)


if __name__ == "__main__":
    main()
