"""VRChat OSC共通クライアント"""

from pythonosc import udp_client

# VRChatデフォルトのOSCポート
VRCHAT_OSC_IP = "127.0.0.1"
VRCHAT_OSC_PORT = 9000

# OSCアドレス
CHATBOX_INPUT = "/chatbox/input"
CHATBOX_TYPING = "/chatbox/typing"
AVATAR_PARAMETERS = "/avatar/parameters/"


def create_client(ip: str = VRCHAT_OSC_IP, port: int = VRCHAT_OSC_PORT) -> udp_client.SimpleUDPClient:
    """VRChat OSCクライアントを作成する"""
    return udp_client.SimpleUDPClient(ip, port)


def send_chatbox(client: udp_client.SimpleUDPClient, message: str, direct: bool = True):
    """Chatboxにメッセージを送信する

    Args:
        client: OSCクライアント
        message: 送信するテキスト（144文字以内）
        direct: True=即時表示、False=入力欄に表示
    """
    client.send_message(CHATBOX_INPUT, [message[:144], direct])


def send_typing(client: udp_client.SimpleUDPClient, is_typing: bool = True):
    """Chatboxのタイピングインジケーターを制御する"""
    client.send_message(CHATBOX_TYPING, is_typing)


def send_parameter(client: udp_client.SimpleUDPClient, name: str, value):
    """アバターパラメータを送信する

    Args:
        client: OSCクライアント
        name: パラメータ名
        value: 値（int, float, bool）
    """
    client.send_message(f"{AVATAR_PARAMETERS}{name}", value)
