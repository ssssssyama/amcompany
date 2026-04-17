"""CDP (Chrome DevTools Protocol) ブラウザマネージャ

実Chromeを --remote-debugging-port で起動し、Playwright の connect_over_cdp() で
接続する。Playwright bundled Chromium ではなく実Chrome の TLS/HTTP2 スタックを
使うことで、プロトコルレベルのbot検知を回避する。

使い方:
    # 他のワーカーから
    from _cdp_browser import ensure_cdp_chrome, CDP_ENDPOINT

    ensure_cdp_chrome()  # Chrome起動（既に起動中ならスキップ）
    browser = playwright.chromium.connect_over_cdp(CDP_ENDPOINT)

    # 単体テスト
    python _cdp_browser.py          # Chrome起動→接続テスト→終了
"""

import atexit
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CDP_PORT = 9222
CDP_ENDPOINT = f"http://127.0.0.1:{CDP_PORT}"

_LOCAL_DATA_DIR = Path.home() / ".kaitori-viewer"
_CDP_USER_DATA = _LOCAL_DATA_DIR / "cdp_chrome_profile"
_CDP_PID_FILE = _LOCAL_DATA_DIR / "cdp_chrome.pid"
_PROFILE_SYNC_MARKER = _CDP_USER_DATA / ".last_sync"

# ユーザーの実ブラウザプロファイルパス（Brave優先）
_USER_BRAVE_PROFILE = Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "User Data"
_USER_CHROME_PROFILE = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"

# ブラウザ検索パス (Windows) — Brave優先（Chromeより検知されにくい）
_BROWSER_CANDIDATES = [
    # Brave
    os.path.join(os.environ.get("PROGRAMFILES", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
    # Chrome
    os.path.join(os.environ.get("PROGRAMFILES", ""), "Google", "Chrome", "Application", "chrome.exe"),
    os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google", "Chrome", "Application", "chrome.exe"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
]


def _sync_user_profile():
    """ユーザーの実ChromeプロファイルからCookie等をCDPプロファイルにコピーする。

    空のプロファイルだとWAFにブロックされるため、実プロファイルのセッションデータを
    コピーして「既存ユーザー」のように見せる。

    コピー対象（セッション系のみ、パスワード等は除外）:
    - Cookies: ログインセッション、トラッキングCookie
    - Network: HSTS、ネットワーク設定
    - Web Data: オートフィル（フォーム入力履歴）
    - Preferences: ブラウザ設定
    - Secure Preferences: セキュリティ設定
    - Local State: (User Data直下) ブラウザ全体設定

    24時間以内に同期済みならスキップ。
    """
    # Brave → Chrome の順で実プロファイルを探す
    user_profile = None
    for profile_dir in [_USER_BRAVE_PROFILE, _USER_CHROME_PROFILE]:
        if (profile_dir / "Default").exists():
            user_profile = profile_dir
            break
    if user_profile is None:
        logger.warning("実ブラウザプロファイルが見つかりません")
        return

    src_default = user_profile / "Default"

    # 24時間以内に同期済みならスキップ
    if _PROFILE_SYNC_MARKER.exists():
        age = time.time() - _PROFILE_SYNC_MARKER.stat().st_mtime
        if age < 86400:  # 24時間
            return

    dst_default = _CDP_USER_DATA / "Default"
    dst_default.mkdir(parents=True, exist_ok=True)

    copied = 0

    # 1. Default/ 直下のファイル（パスワード・Login Data は除外）
    sync_files = ["Web Data", "Preferences", "Secure Preferences"]
    for name in sync_files:
        src = src_default / name
        dst = dst_default / name
        if src.exists():
            try:
                shutil.copy2(str(src), str(dst))
                copied += 1
            except (OSError, PermissionError) as e:
                logger.debug("プロファイルコピースキップ(%s): %s", name, e)

    # 2. Default/Network/ ディレクトリ（Cookieはここに格納される）
    src_network = src_default / "Network"
    dst_network = dst_default / "Network"
    if src_network.exists():
        dst_network.mkdir(parents=True, exist_ok=True)
        network_files = ["Cookies", "TransportSecurity", "Network Persistent State"]
        for name in network_files:
            src = src_network / name
            dst = dst_network / name
            if src.exists():
                try:
                    shutil.copy2(str(src), str(dst))
                    copied += 1
                except (OSError, PermissionError) as e:
                    logger.debug("Networkコピースキップ(%s): %s", name, e)

    # 3. Local State (User Data 直下)
    src_local = user_profile / "Local State"
    dst_local = _CDP_USER_DATA / "Local State"
    if src_local.exists():
        try:
            shutil.copy2(str(src_local), str(dst_local))
            copied += 1
        except (OSError, PermissionError):
            pass

    if copied > 0:
        _PROFILE_SYNC_MARKER.parent.mkdir(parents=True, exist_ok=True)
        _PROFILE_SYNC_MARKER.write_text(str(time.time()))
        logger.info("Chromeプロファイル同期完了: %d件のファイルをコピー", copied)


def _find_browser() -> str | None:
    """インストール済みのChromiumベースブラウザを返す（Brave優先）"""
    for path in _BROWSER_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    found = shutil.which("brave") or shutil.which("google-chrome") or shutil.which("chrome")
    return found


def _is_port_open(port: int) -> bool:
    """指定ポートで接続を受け付けているか確認"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


def _is_cdp_responsive() -> bool:
    """CDPエンドポイントが応答するか確認"""
    try:
        import urllib.request
        req = urllib.request.Request(f"{CDP_ENDPOINT}/json/version", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            return "webSocketDebuggerUrl" in data
    except Exception:
        return False


def _kill_stale_chrome():
    """PIDファイルに記録された古いChromeプロセスを終了"""
    if not _CDP_PID_FILE.exists():
        return
    try:
        pid = int(_CDP_PID_FILE.read_text().strip())
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            os.kill(pid, 9)
    except (ValueError, OSError, subprocess.SubprocessError):
        pass
    finally:
        try:
            _CDP_PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass


_chrome_proc: subprocess.Popen | None = None


def _cleanup():
    """プロセス終了時にChromeをクリーンアップ"""
    global _chrome_proc
    if _chrome_proc is not None:
        try:
            _chrome_proc.terminate()
            _chrome_proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            try:
                _chrome_proc.kill()
            except OSError:
                pass
        _chrome_proc = None
    _CDP_PID_FILE.unlink(missing_ok=True)


atexit.register(_cleanup)


def ensure_cdp_chrome(headless: bool = False) -> bool:
    """CDPポートでChromeが応答可能な状態を保証する。

    既に起動中なら何もしない。未起動なら実Chromeを起動する。

    Args:
        headless: True で --headless=new を使用。
                  False（デフォルト）で画面外に配置した通常ウィンドウ。
                  headless=new は一部サイトでブロックされるため、
                  デフォルトはheadedモード。

    Returns:
        True: CDPが応答可能
        False: Chrome起動失敗
    """
    global _chrome_proc

    # 既にCDPが応答するなら何もしない
    if _is_cdp_responsive():
        return True

    # ポートは開いているがCDPが応答しない → 古いプロセスをクリーンアップ
    if _is_port_open(CDP_PORT):
        _kill_stale_chrome()
        time.sleep(1)

    chrome_path = _find_browser()
    if not chrome_path:
        logger.error("Chromiumベースブラウザが見つかりません（Brave/Chrome）")
        return False

    _LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 実Chromeプロファイルからセッションデータを同期
    _sync_user_profile()

    args = [
        chrome_path,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={_CDP_USER_DATA}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-default-apps",
        "--disable-sync",
        "--disable-translate",
        "--metrics-recording-only",
        "--no-service-autorun",
    ]

    if headless:
        args.append("--headless=new")
    else:
        # headedモード: 画面外に配置して見えないようにする
        args.append("--window-position=-32000,-32000")
        args.append("--window-size=1,1")

    # メモリ節約（--disable-extensions は除外: 拡張が入っている方が自然に見える）
    args.extend([
        "--disable-gpu",
        "--disable-dev-shm-usage",
    ])

    try:
        _chrome_proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _CDP_PID_FILE.write_text(str(_chrome_proc.pid))
    except (OSError, FileNotFoundError) as e:
        logger.error("Chrome起動失敗: %s", e)
        return False

    # CDPが応答するまで待機（最大10秒）
    for _ in range(20):
        time.sleep(0.5)
        if _is_cdp_responsive():
            logger.info("CDP Chrome起動完了 (pid=%d, port=%d)", _chrome_proc.pid, CDP_PORT)
            return True

    logger.error("CDP Chrome起動タイムアウト（10秒以内に応答なし）")
    _cleanup()
    return False


def shutdown_cdp_chrome():
    """CDPChromeを明示的に終了する"""
    _cleanup()


# --- 単体テスト ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("=== CDP Browser Manager テスト ===")

    chrome = _find_browser()
    if chrome:
        print(f"Browser: {chrome}")
    else:
        print("ERROR: ブラウザが見つかりません")
        sys.exit(1)

    print(f"CDPポート: {CDP_PORT}")
    print("Chrome起動中...")

    if ensure_cdp_chrome(headless=False):
        print("CDP接続OK")

        # Playwrightで接続テスト
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(CDP_ENDPOINT)
                context = browser.new_context()
                page = context.new_page()
                page.goto("https://example.com", timeout=10000)
                title = page.title()
                print(f"テストページタイトル: {title}")
                page.close()
                context.close()
                browser.close()
            print("Playwright CDP接続テスト成功")
        except Exception as e:
            print(f"Playwright接続テスト失敗: {e}")
    else:
        print("ERROR: CDP Chrome起動失敗")
        sys.exit(1)

    print("Chrome終了中...")
    shutdown_cdp_chrome()
    print("完了")
