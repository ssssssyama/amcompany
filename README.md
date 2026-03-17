# AM Company ツール集

VRChat向けツールとテストエビデンス自動化ツールをまとめたリポジトリです。

---

## ツール一覧

### VRChat向けツール（Python + OSC）

| ツール | 説明 | 難易度 |
|--------|------|--------|
| [Chatbox デコレーター](tools/chatbox-decorator/) | Chatboxテキストを装飾フレームで囲む | 簡単 |
| [おみくじBot](tools/omikuji-bot/) | 今日の運勢をChatboxに表示 | 簡単 |
| [OSCタイマー](tools/osc-timer/) | タイマー・ストップウォッチ・ポモドーロ | 簡単 |

### AI系ツール（GPU推奨）

| ツール | 説明 | 難易度 |
|--------|------|--------|
| [足音AI生成](tools/footstep-generator/) | AIで足音効果音をローカル生成 | やや難 |
| [テクスチャ高画質化](tools/texture-upscaler/) | テクスチャを4倍にアップスケール | やや難 |

### その他

| ツール | 説明 | 難易度 |
|--------|------|--------|
| [サムネイル生成](tools/thumbnail-generator/) | BOOTH用サムネイルを自動生成 | 簡単 |
| [テストエビデンス](tools/test-evidence/) | テスト仕様書→操作→エビデンスの自動化 | 中級 |

### 社会貢献ツール

| ツール | 説明 | 難易度 |
|--------|------|--------|
| [闇バイト通報支援](yami-baito-reporter/) | 怪しい求人の危険度チェック＆通報先ガイド | 簡単 |

---

## はじめかた（初心者の方へ）

### ステップ1: Pythonのインストール

Pythonがまだ入っていない方は、以下からインストールしてください。

1. https://www.python.org/downloads/ にアクセス
2. 「Download Python 3.x.x」をクリック
3. インストーラーを起動
4. **「Add Python to PATH」にチェックを入れてからInstallを押す**（重要！）

インストールできたか確認するには、コマンドプロンプト（Windows）またはターミナル（Mac）を開いて以下を入力してください:

```
python --version
```

バージョン番号が表示されればOKです。

### ステップ2: コマンドプロンプト/ターミナルの開き方

**Windows:**
- キーボードの `Windows + R` を押す
- `cmd` と入力してEnter

**Mac:**
- Spotlight（`Command + Space`）で「ターミナル」と検索して開く

### ステップ3: このフォルダに移動

ダウンロードしたフォルダの場所に移動します:

```
cd ダウンロードしたフォルダのパス
```

例: `cd C:\Users\あなたの名前\Downloads\amcompany`

### ステップ4: セットアップスクリプトを実行

**Windows:**
```
setup.bat
```

**Mac/Linux:**
```
bash setup.sh
```

これで必要なものが自動的にインストールされます。

### ステップ5: ツールを起動

**GUIで起動したい場合（おすすめ）:**

```
python launcher.py
```

ウィンドウが開くので、使いたいツールをクリックするだけです。

**コマンドラインで使いたい場合:**

各ツールのREADMEを参照してください。

---

## VRChat OSCの設定方法

VRChat向けツールを使うには、VRChat側でOSCを有効にする必要があります。

1. VRChatを起動してワールドに入る
2. Action Menu（メニュー）を開く
3. **Options** → **OSC** → **Enabled** をONにする
4. 完了！（ツールが自動で通信します）

うまく動かない場合は:
- VRChatを再起動してみてください
- OSCの設定をOFF→ONに切り替えてみてください
- VRChatとツールを同じPCで動かしてください

---

## よくあるエラーと対処法

### `python` コマンドが見つからない

**原因**: Pythonがインストールされていないか、PATHが通っていない

**対処法**:
- Pythonをインストールし直す（「Add Python to PATH」にチェックを入れる）
- Windowsの場合は `python3` の代わりに `py` でも試してみてください

### `ModuleNotFoundError: No module named 'pythonosc'`

**原因**: 必要なパッケージがインストールされていない

**対処法**:
```
pip install python-osc
```
または `setup.bat`（Windows）/ `bash setup.sh`（Mac/Linux）を実行してください。

### `ModuleNotFoundError: No module named 'PIL'`

**対処法**:
```
pip install Pillow
```

### `OSError: [Errno 99]` や接続エラー

**原因**: VRChatが起動していないか、OSCが有効になっていない

**対処法**:
- VRChatを起動してワールドに入っていることを確認
- VRChatの設定でOSCが Enabled になっているか確認

### GPUが認識されない（AI系ツール）

**原因**: CUDAドライバが入っていない

**対処法**:
- `texture-upscaler` は `--cpu` オプションでCPUでも動作します（ただし低速）
- GPUを使う場合は https://developer.nvidia.com/cuda-downloads からCUDAをインストール

### 文字化け

**対処法**:
- Windowsのコマンドプロンプトで以下を実行してからツールを起動:
  ```
  chcp 65001
  ```
