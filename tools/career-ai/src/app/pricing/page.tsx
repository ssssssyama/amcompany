import Link from "next/link";

const plans = [
  {
    name: "無料プラン",
    price: "0",
    period: "",
    description: "まずは試してみたい方に",
    features: [
      "月3回まで書類生成",
      "職務経歴書ジェネレーター",
      "基本テンプレート",
      "テキストコピー",
    ],
    cta: "無料で始める",
    href: "/resume/new",
    highlighted: false,
  },
  {
    name: "スタンダード",
    price: "980",
    period: "/月",
    description: "本格的に転職活動をする方に",
    features: [
      "無制限の書類生成",
      "職務経歴書ジェネレーター",
      "志望動機ジェネレーター",
      "全テンプレート利用可能",
      "PDF/Wordダウンロード",
      "生成履歴の保存",
    ],
    cta: "スタンダードを始める",
    href: "/resume/new",
    highlighted: true,
  },
  {
    name: "プレミアム",
    price: "1,980",
    period: "/月",
    description: "万全の準備で臨みたい方に",
    features: [
      "スタンダードの全機能",
      "自己PR添削・改善提案",
      "業界別最適化テンプレート",
      "優先サポート",
      "面接対策機能（近日公開）",
    ],
    cta: "プレミアムを始める",
    href: "/resume/new",
    highlighted: false,
  },
];

export default function PricingPage() {
  return (
    <div className="py-16 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-4">
            料金プラン
          </h1>
          <p className="text-gray-500 text-lg">
            転職成功への投資。年収アップに比べれば、月980円は最高のコスパ。
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={`rounded-2xl p-8 ${
                plan.highlighted
                  ? "bg-primary text-white ring-4 ring-primary/20 scale-105"
                  : "bg-white border border-gray-200"
              }`}
            >
              <h3
                className={`text-lg font-semibold ${plan.highlighted ? "text-blue-100" : "text-gray-500"}`}
              >
                {plan.name}
              </h3>
              <div className="mt-4 flex items-baseline">
                <span
                  className={`text-4xl font-bold ${plan.highlighted ? "text-white" : "text-gray-900"}`}
                >
                  {plan.price === "0" ? "無料" : `¥${plan.price}`}
                </span>
                {plan.period && (
                  <span
                    className={`ml-1 ${plan.highlighted ? "text-blue-200" : "text-gray-500"}`}
                  >
                    {plan.period}
                  </span>
                )}
              </div>
              <p
                className={`mt-2 text-sm ${plan.highlighted ? "text-blue-100" : "text-gray-500"}`}
              >
                {plan.description}
              </p>

              <ul className="mt-6 space-y-3">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2 text-sm">
                    <svg
                      className={`w-5 h-5 flex-shrink-0 ${plan.highlighted ? "text-blue-200" : "text-primary"}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M5 13l4 4L19 7"
                      />
                    </svg>
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>

              <Link
                href={plan.href}
                className={`mt-8 block w-full text-center py-3 rounded-lg font-semibold transition-colors ${
                  plan.highlighted
                    ? "bg-white text-primary hover:bg-blue-50"
                    : "bg-primary text-white hover:bg-primary-dark"
                }`}
              >
                {plan.cta}
              </Link>
            </div>
          ))}
        </div>

        <div className="mt-16 text-center">
          <h3 className="text-xl font-semibold text-gray-900 mb-4">
            よくある質問
          </h3>
          <div className="max-w-2xl mx-auto space-y-6 text-left">
            <div>
              <h4 className="font-medium text-gray-900">
                無料プランだけでも使えますか？
              </h4>
              <p className="mt-1 text-sm text-gray-500">
                はい。月3回まで職務経歴書を生成できます。まずは無料でお試しください。
              </p>
            </div>
            <div>
              <h4 className="font-medium text-gray-900">
                いつでも解約できますか？
              </h4>
              <p className="mt-1 text-sm text-gray-500">
                はい。いつでもワンクリックで解約でき、違約金は一切ありません。
              </p>
            </div>
            <div>
              <h4 className="font-medium text-gray-900">
                生成された内容のクオリティは？
              </h4>
              <p className="mt-1 text-sm text-gray-500">
                最新のAI技術を活用し、日本の転職市場に特化したプロンプトで高品質な文書を生成します。もちろん、生成後にご自身で編集・調整も可能です。
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
