"""通知モジュール: LINE / Discord / デスクトップ通知の統合

利益商品発見時・再入荷検知時にユーザーにプッシュ通知する。
.env で各チャネルを有効化可能（未設定のチャネルはサイレントにスキップ）。

環境変数:
    LINE_NOTIFY_TOKEN    - LINE Notify の Personal Access Token
    DISCORD_WEBHOOK_URL  - Discord Webhook URL
    DESKTOP_NOTIFY=true  - Windowsデスクトップ通知を有効化（既定は有効）

使い方:
    from notifier import notify_profit, notify_restock
    notify_profit(jan="4549292167382", name="Canon EOS R50",
                  price=95980, profit=12000, url="https://...")
    notify_restock(jan="4549292167382", name="Canon EOS R50",
                   price=95980, url="https://...")
"""

import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()
LINE_NOTIFY_TOKEN = os.getenv("LINE_NOTIFY_TOKEN", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DESKTOP_NOTIFY = os.getenv("DESKTOP_NOTIFY", "true").lower() in ("true", "1", "yes")

# 同一JANへの重複通知抑制（30分）
_NOTIFIED_FILE = Path.home() / ".kaitori-viewer" / "notified.json"
_DEDUP_SECONDS = 30 * 60


def _load_notified() -> dict:
    import json
    if not _NOTIFIED_FILE.exists():
        return {}
    try:
        return json.loads(_NOTIFIED_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_notified(d: dict) -> None:
    import json
    _NOTIFIED_FILE.parent.mkdir(parents=True, exist_ok=True)
    _NOTIFIED_FILE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _is_duplicate(jan: str, event: str) -> bool:
    """同一 (jan, event) が 30分以内に通知されたか"""
    import time
    key = f"{event}:{jan}"
    notified = _load_notified()
    last = notified.get(key, 0)
    return (time.time() - last) < _DEDUP_SECONDS


def _mark_notified(jan: str, event: str) -> None:
    import time
    key = f"{event}:{jan}"
    notified = _load_notified()
    notified[key] = int(time.time())
    # 古いエントリ（24h以上前）を掃除
    cutoff = time.time() - 24 * 3600
    notified = {k: v for k, v in notified.items() if v > cutoff}
    _save_notified(notified)


def _send_line(text: str) -> bool:
    """LINE Notify で送信"""
    if not LINE_NOTIFY_TOKEN:
        return False
    try:
        r = requests.post(
            "https://notify-api.line.me/api/notify",
            headers={"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"},
            data={"message": text},
            timeout=5,
        )
        return r.status_code == 200
    except requests.RequestException as e:
        logger.debug("LINE通知失敗: %s", e)
        return False


def _send_discord(text: str) -> bool:
    """Discord Webhook で送信"""
    if not DISCORD_WEBHOOK_URL:
        return False
    try:
        r = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": text[:2000]},  # Discord制限
            timeout=5,
        )
        return r.status_code in (200, 204)
    except requests.RequestException as e:
        logger.debug("Discord通知失敗: %s", e)
        return False


def _send_desktop(title: str, text: str) -> bool:
    """Windowsデスクトップ通知（Plyer or win10toast）"""
    if not DESKTOP_NOTIFY:
        return False
    try:
        # Plyer 優先（クロスプラットフォーム）
        from plyer import notification
        notification.notify(title=title, message=text[:250], timeout=10)
        return True
    except ImportError:
        pass
    try:
        # Windows native via PowerShell
        import subprocess
        ps = (
            '[Windows.UI.Notifications.ToastNotificationManager, '
            'Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; '
            '[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, '
            'ContentType = WindowsRuntime] > $null; '
            f'$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; '
            f'$xml.LoadXml("<toast><visual><binding template=\\"ToastGeneric\\">'
            f'<text>{title}</text><text>{text[:200]}</text>'
            f'</binding></visual></toast>"); '
            f'[Windows.UI.Notifications.ToastNotificationManager]::'
            f'CreateToastNotifier("kaitori-viewer").Show('
            f'[Windows.UI.Notifications.ToastNotification]::new($xml))'
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as e:
        logger.debug("デスクトップ通知失敗: %s", e)
        return False


def _dispatch(title: str, text: str) -> list[str]:
    """全チャネルに送信。成功したチャネル名のリストを返す"""
    ok = []
    if _send_line(text):
        ok.append("LINE")
    if _send_discord(f"**{title}**\n{text}"):
        ok.append("Discord")
    if _send_desktop(title, text):
        ok.append("Desktop")
    return ok


def notify_profit(
    jan: str,
    name: str,
    price: int,
    profit: int,
    url: str = "",
    buyback_shop: str = "",
    ec_source: str = "",
) -> list[str]:
    """利益商品発見通知"""
    if _is_duplicate(jan, "profit"):
        return []
    text = (
        f"💰 利益商品 +{profit:,}円\n"
        f"{name[:60]}\n"
        f"EC {ec_source}: {price:,}円\n"
        f"買取: {buyback_shop}\n"
        f"{url}"
    )
    ok = _dispatch(f"利益商品 +{profit:,}円", text)
    if ok:
        _mark_notified(jan, "profit")
        logger.info("[通知] 利益商品 %s → %s", jan, ",".join(ok))
    return ok


def notify_restock(
    jan: str,
    name: str,
    price: int,
    url: str = "",
) -> list[str]:
    """再入荷通知（戦略Gで在庫切れ商品が復活したとき）"""
    if _is_duplicate(jan, "restock"):
        return []
    text = (
        f"🔔 再入荷\n"
        f"{name[:60]}\n"
        f"価格: {price:,}円\n"
        f"{url}"
    )
    ok = _dispatch(f"再入荷: {name[:30]}", text)
    if ok:
        _mark_notified(jan, "restock")
        logger.info("[通知] 再入荷 %s → %s", jan, ",".join(ok))
    return ok


def notify_tight_stock(
    jan: str,
    name: str,
    stock_count: int,
    price: int,
    url: str = "",
) -> list[str]:
    """在庫切迫通知（残り○点の利益商品）"""
    if _is_duplicate(jan, f"tight-{stock_count}"):
        return []
    text = (
        f"⚠️ 在庫残り{stock_count}点\n"
        f"{name[:60]}\n"
        f"価格: {price:,}円\n"
        f"{url}"
    )
    ok = _dispatch(f"在庫切迫 残り{stock_count}点", text)
    if ok:
        _mark_notified(jan, f"tight-{stock_count}")
        logger.info("[通知] 在庫切迫 %s → %s", jan, ",".join(ok))
    return ok


if __name__ == "__main__":
    # テスト通知
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("通知チャネル設定:")
    print(f"  LINE_NOTIFY_TOKEN: {'設定済' if LINE_NOTIFY_TOKEN else '未設定'}")
    print(f"  DISCORD_WEBHOOK_URL: {'設定済' if DISCORD_WEBHOOK_URL else '未設定'}")
    print(f"  DESKTOP_NOTIFY: {'有効' if DESKTOP_NOTIFY else '無効'}")
    print()
    result = notify_profit(
        jan="TEST000000000",
        name="テスト商品 Canon EOS R50",
        price=95980,
        profit=12000,
        url="https://example.com",
        buyback_shop="ルデヤ",
        ec_source="楽天",
    )
    print(f"通知結果: {result}")
