// Free plan limits
export const FREE_PLAN_LIMIT = 3; // generations per month

export const PLANS = {
  free: {
    name: "無料プラン",
    price: 0,
    monthlyLimit: 3,
    features: ["職務経歴書ジェネレーター", "基本テンプレート", "テキストコピー"],
  },
  standard: {
    name: "スタンダード",
    price: 980,
    monthlyLimit: Infinity,
    features: [
      "無制限の書類生成",
      "職務経歴書ジェネレーター",
      "志望動機ジェネレーター",
      "全テンプレート利用可能",
      "PDF/Wordダウンロード",
      "生成履歴の保存",
    ],
  },
  premium: {
    name: "プレミアム",
    price: 1980,
    monthlyLimit: Infinity,
    features: [
      "スタンダードの全機能",
      "自己PR添削・改善提案",
      "業界別最適化テンプレート",
      "優先サポート",
      "面接対策機能（近日公開）",
    ],
  },
} as const;

// Stripe Price IDs (to be configured after Stripe setup)
export const STRIPE_PRICES = {
  standard: process.env.NEXT_PUBLIC_STRIPE_STANDARD_PRICE_ID || "",
  premium: process.env.NEXT_PUBLIC_STRIPE_PREMIUM_PRICE_ID || "",
} as const;
