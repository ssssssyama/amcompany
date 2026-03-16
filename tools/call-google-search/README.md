# 着信Google検索

着信時に電話番号をGoogleで自動検索するAndroidアプリです。
詐欺電話や不動産営業などの迷惑電話を、出る前に判別できます。

## 機能

- 着信時に電話番号を自動でGoogle検索
- ブラウザで検索結果を表示（迷惑電話データベースの情報が確認可能）
- ワンタップで機能のON/OFF切り替え

## 必要環境

- Android 10以上（API 29+）
- Android Studio（ビルド用）

## セットアップ

### Android Studio でビルド

1. Android Studio で `tools/call-google-search` フォルダを開く
2. Gradle Sync を実行
3. 実機またはエミュレータにインストール

### コマンドラインでビルド

```bash
cd tools/call-google-search
./gradlew assembleDebug
```

APK は `app/build/outputs/apk/debug/app-debug.apk` に生成されます。

## 使い方

1. アプリをインストールして起動
2. 電話の権限（READ_PHONE_STATE, READ_CALL_LOG）を許可
3. スイッチをONにする
4. 着信があると自動的にブラウザでGoogle検索が開く
5. 検索結果で迷惑電話かどうかを確認し、電話に出るか判断する

## 必要な権限

| 権限 | 用途 |
|------|------|
| `READ_PHONE_STATE` | 着信の検知 |
| `READ_CALL_LOG` | 着信番号の取得（Android 10+で必須） |

## ライセンス

MIT License
