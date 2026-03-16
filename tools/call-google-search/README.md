# 着信Google検索

着信時に電話番号をGoogleで自動検索するAndroidアプリです。
詐欺電話や不動産営業などの迷惑電話を、出る前に判別できます。

## 機能

- 着信時に電話番号のGoogle検索通知を自動表示
- 通知をタップするとブラウザで検索結果を確認できる
- ワンタップで機能のON/OFF切り替え
- Android 16 対応（通知方式でバックグラウンド制限を回避）

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
2. 必要な権限（電話・通話履歴・通知）を許可
3. スイッチをONにする
4. 着信があると通知が表示される
5. 通知をタップするとブラウザでGoogle検索が開く
6. 検索結果で迷惑電話かどうかを確認し、電話に出るか判断する

## 必要な権限

| 権限 | 用途 |
|------|------|
| `READ_PHONE_STATE` | 着信の検知 |
| `READ_CALL_LOG` | 着信番号の取得（Android 10+で必須） |
| `POST_NOTIFICATIONS` | 検索通知の表示（Android 13+で必須） |

## ライセンス

MIT License
