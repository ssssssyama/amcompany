# Shorts Speed Player

YouTube ショート動画を倍速再生できる Android アプリです。

## 機能

- YouTube Shorts の URL を貼り付けて再生
- ショート一覧をブラウズ
- 再生速度を変更: 0.5x, 0.75x, 1x, 1.25x, 1.5x, 2x, 3x
- ショートをスワイプで切り替えても速度設定が維持される
- YouTube Shorts URL の共有インテントに対応
- フルスクリーン再生対応

## 技術仕様

- **言語**: Kotlin
- **最小 SDK**: 24 (Android 7.0)
- **ターゲット SDK**: 34
- **アーキテクチャ**: WebView + JavaScript インジェクション

## 仕組み

WebView で YouTube Shorts ページを読み込み、JavaScript を注入して HTML5 `<video>` 要素の `playbackRate` を制御します。`MutationObserver` により、ショート間のスクロール時に動的に生成される新しい動画要素にも速度設定が自動適用されます。

## ビルド方法

1. Android Studio で本プロジェクトを開く
2. Gradle Sync を実行
3. Run ボタンでデバイスにインストール

## 注意事項

- インターネット接続が必要です
- YouTube の仕様変更により動作しなくなる場合があります
