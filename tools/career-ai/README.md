# キャリアAI — AI職務経歴書・志望動機ジェネレーター

転職活動者向けのAI書類作成支援Webアプリ。

## 機能

- **AI職務経歴書ジェネレーター**: 職歴+応募先情報 → 最適化された職務経歴書
- **AI志望動機ジェネレーター**: 企業情報+経歴 → カスタマイズされた志望動機
- **自己PR添削**: AIによる添削・改善提案
- **PDF保存**: ブラウザの印刷機能でPDF出力

## 技術スタック

- Next.js 16 (App Router) + TypeScript
- Tailwind CSS v4
- Claude API (Anthropic)
- Supabase (DB + Auth) — 予定
- Stripe (決済) — 予定

## セットアップ

```bash
cd tools/career-ai
npm install
cp .env.example .env.local
# .env.local に ANTHROPIC_API_KEY を設定
npm run dev
```

## 環境変数

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API キー |
| `ANTHROPIC_MODEL` | No | モデル名（デフォルト: claude-sonnet-4-20250514） |

## 開発

```bash
npm run dev    # 開発サーバー起動
npm run build  # プロダクションビルド
npm run lint   # ESLint実行
```

## ページ構成

| パス | 説明 |
|------|------|
| `/` | ランディングページ |
| `/resume/new` | AI職務経歴書ジェネレーター |
| `/motivation` | AI志望動機ジェネレーター |
| `/review` | 自己PR添削 |
| `/pricing` | 料金プラン |
| `/api/generate` | AI生成API (POST) |

## 料金プラン

| プラン | 月額 | 内容 |
|--------|------|------|
| 無料 | 0円 | 月3回まで生成 |
| スタンダード | 980円/月 | 無制限生成 + 志望動機 + PDF |
| プレミアム | 1,980円/月 | スタンダード + 添削 + 面接対策（予定） |
