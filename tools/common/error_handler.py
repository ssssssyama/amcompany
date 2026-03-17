"""日本語エラーメッセージハンドラー — 初心者にもわかりやすいエラー表示"""

import sys
import traceback


# よくあるエラーの日本語メッセージマッピング
ERROR_MESSAGES = {
    "ModuleNotFoundError": {
        "pythonosc": (
            "python-osc パッケージがインストールされていません。\n"
            "以下のコマンドを実行してください:\n"
            "  pip install python-osc\n"
            "または setup.bat（Windows）/ bash setup.sh（Mac/Linux）を実行してください。"
        ),
        "PIL": (
            "Pillow パッケージがインストールされていません。\n"
            "以下のコマンドを実行してください:\n"
            "  pip install Pillow"
        ),
        "torch": (
            "PyTorch がインストールされていません。\n"
            "以下のコマンドを実行してください:\n"
            "  NVIDIA GPU: pip install -r requirements-footstep.txt\n"
            "  AMD GPU:    pip install torch --index-url https://download.pytorch.org/whl/rocm6.1"
        ),
        "realesrgan": (
            "Real-ESRGAN パッケージがインストールされていません。\n"
            "以下のコマンドを実行してください:\n"
            "  pip install -r requirements-upscaler.txt"
        ),
        "stable_audio_tools": (
            "Stable Audio Tools パッケージがインストールされていません。\n"
            "以下のコマンドを実行してください:\n"
            "  pip install -r requirements-footstep.txt"
        ),
    },
    "OSError": {
        "99": (
            "ネットワーク接続に失敗しました。\n"
            "VRChatが起動しているか確認してください。\n"
            "VRChatの設定でOSCが有効になっているか確認してください:\n"
            "  Action Menu → Options → OSC → Enabled"
        ),
    },
    "ConnectionRefusedError": {
        "": (
            "VRChatへの接続が拒否されました。\n"
            "VRChatが起動してワールドに入っているか確認してください。\n"
            "OSCが有効になっているか確認してください:\n"
            "  Action Menu → Options → OSC → Enabled"
        ),
    },
    "FileNotFoundError": {
        "": (
            "ファイルが見つかりません。\n"
            "ファイルのパスが正しいか確認してください。"
        ),
    },
}


def get_friendly_message(exc):
    """例外から日本語メッセージを取得"""
    exc_type = type(exc).__name__
    exc_msg = str(exc)

    if exc_type in ERROR_MESSAGES:
        type_map = ERROR_MESSAGES[exc_type]
        # モジュール名を抽出して一致するか確認
        for key, message in type_map.items():
            if key == "" or key in exc_msg:
                return message

    return None


def friendly_error_handler(tool_name="ツール"):
    """デコレータ: main関数のエラーを日本語で表示する"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except KeyboardInterrupt:
                print(f"\n{tool_name}を終了します。")
                sys.exit(0)
            except Exception as exc:
                friendly = get_friendly_message(exc)
                print("")
                print("=" * 50)
                print(f"  {tool_name} でエラーが発生しました")
                print("=" * 50)
                if friendly:
                    print("")
                    print(friendly)
                else:
                    print("")
                    print(f"エラーの種類: {type(exc).__name__}")
                    print(f"詳細: {exc}")
                    print("")
                    print("このエラーが解決しない場合は、")
                    print("エラーメッセージを開発者に報告してください。")
                print("")
                print("--- 技術的な詳細（開発者向け）---")
                traceback.print_exc()
                sys.exit(1)
        return wrapper
    return decorator
