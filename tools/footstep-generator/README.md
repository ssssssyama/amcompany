# 足音AI生成ツール

Stable Audio Open を使って、VRChatアバター用の足音効果音をローカルAIで生成するツール。

## 必要環境

- Python 3.9+
- CUDA対応GPU（VRAM 8GB以上推奨）
- ディスク容量: モデル約3.5GB

## セットアップ

```bash
pip install -r requirements-footstep.txt
```

初回実行時にモデルが自動ダウンロードされます（Hugging Faceアカウントが必要な場合があります）。

## 使い方

```bash
# 全サーフェス（10種類×3バリエーション = 30ファイル）を生成
python tools/footstep-generator/generate.py

# 特定のサーフェスのみ
python tools/footstep-generator/generate.py --surfaces wood stone grass

# バリエーション数を変更
python tools/footstep-generator/generate.py --variations 5

# 音の長さを変更（秒）
python tools/footstep-generator/generate.py --duration 1.0

# 出力先を指定
python tools/footstep-generator/generate.py --output ./my_sounds

# 利用可能なサーフェス一覧
python tools/footstep-generator/generate.py --list-surfaces
```

## サポートするサーフェス

| ID | 名前 | 説明 |
|----|------|------|
| wood | 木の床 | 室内の木製フローリング |
| stone | 石畳 | 石の床・石畳 |
| grass | 草地 | 屋外の草むら |
| metal | 金属 | 金属グレーチング |
| gravel | 砂利 | 砂利道 |
| snow | 雪 | 雪の上 |
| water | 水たまり | 浅い水たまり |
| carpet | カーペット | 室内カーペット |
| sand | 砂浜 | ビーチの砂 |
| tile | タイル | セラミックタイル |

## 出力

```
output/
├── manifest.json     # 生成ファイルの一覧
├── wood/
│   ├── wood_01.wav
│   ├── wood_02.wav
│   └── wood_03.wav
├── stone/
│   └── ...
└── ...
```

`manifest.json` にはサーフェスごとのファイル一覧が含まれ、Unity側での読み込みに利用できます。

## ライセンス

- **Stable Audio Open**: [Stability AI Community License](https://stability.ai/license)
  - 年商$1M未満: 無料で商用利用可
  - それ以上: Stability AIへの登録が必要
- **生成された音源**: ユーザー自身のPCで生成するため、再配布制限の対象外
