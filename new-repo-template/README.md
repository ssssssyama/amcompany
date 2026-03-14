# vrchat-tools-kit

VRChat向けOSCツールキット。VRChat上で使える便利ツールを開発・管理するためのリポジトリです。

## 構成

```
tools/
├── common/          # 共通ユーティリティ（OSCクライアント等）
│   ├── __init__.py
│   └── osc_client.py
└── <tool-name>/     # 各ツール
    ├── main.py
    └── README.md
docs/                # ドキュメント
```

## セットアップ

```bash
# 依存パッケージのインストール
pip install -r requirements.txt
```

## ツールの追加方法

1. `tools/` 配下に新しいディレクトリを作成
2. `main.py` にツールのメイン処理を実装
3. 共通OSCクライアントを利用する場合:

```python
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common.osc_client import create_client, send_chatbox, send_parameter
```

4. `README.md` に使い方を記載

## 共通OSCクライアント

`tools/common/osc_client.py` にVRChat OSC通信の共通機能があります:

- `create_client(ip, port)` — OSCクライアント作成
- `send_chatbox(client, message)` — Chatboxにメッセージ送信
- `send_typing(client, is_typing)` — タイピングインジケーター制御
- `send_parameter(client, name, value)` — アバターパラメータ送信

## 動作環境

- Python 3.9以上
- VRChat（OSC有効化済み）
