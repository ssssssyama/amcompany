# Asset Accumulation Agent

24時間エージェントを回して換金性のある資産を蓄積するフレームワーク。

## コンセプト

エージェントが1サイクル回るたびに、売れるものが1つ増える。

| Tier | 資産タイプ | 例 |
|------|-----------|-----|
| S | 直接売上 | 音源パック、テクスチャパック、コードテンプレート |
| A | トラフィック導線 | SEO記事、チュートリアル、SNS素材 |
| B | 間接価値 | 市場データ、翻訳メモリ、品質データ |

## セットアップ

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
# config.yaml を編集
```

## 使い方

```bash
# 全エージェント1回実行
python -m src.runner --once

# 指定エージェントのみ
python -m src.runner --agent audio_pack --once

# 24時間稼働
python -m src.runner --daemon

# 蓄積状況レポート
python -m src.runner --stats
```

## エージェント一覧

- **audio_pack**: 音源パック生成（テーマ別足音等）
- **image_variants**: 画像バリエーション生成（テクスチャ等）
- **listing_writer**: 商品説明・メタデータ自動生成
- **seo_content**: SEO記事生成
