import Link from "next/link";

const features = [
  {
    title: "AI職務経歴書ジェネレーター",
    description:
      "職歴とスキルを入力するだけで、応募先企業に最適化された職務経歴書をAIが自動生成。「担当しました」を「推進し、成果を達成」に変換。",
    href: "/resume/new",
    icon: (
      <svg
        className="w-8 h-8"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
    ),
  },
  {
    title: "AI志望動機ジェネレーター",
    description:
      "企業情報と自分の経歴を入力すれば、応募先ごとにカスタマイズされた志望動機を自動生成。使い回し感のない、説得力のある文章に。",
    href: "/motivation",
    icon: (
      <svg
        className="w-8 h-8"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
        />
      </svg>
    ),
  },
  {
    title: "自己PR添削",
    description:
      "あなたの自己PR文をAIが添削。具体性の不足、数値化できる実績の見落としなど、改善ポイントを的確に指摘します。",
    href: "/review",
    icon: (
      <svg
        className="w-8 h-8"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
        />
      </svg>
    ),
  },
];

const steps = [
  {
    step: "1",
    title: "情報を入力",
    description: "職歴・スキル・応募先企業の情報をフォームに入力",
  },
  {
    step: "2",
    title: "AIが自動生成",
    description: "AIが応募先に最適化された書類を数秒で生成",
  },
  {
    step: "3",
    title: "確認・ダウンロード",
    description: "生成された内容を確認・編集し、PDF/Wordでダウンロード",
  },
];

export default function Home() {
  return (
    <div>
      {/* Hero Section */}
      <section className="bg-gradient-to-br from-blue-50 to-indigo-50 py-20 px-4">
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-4xl md:text-5xl font-bold text-gray-900 leading-tight">
            転職書類の作成を
            <br />
            <span className="text-primary">AIが自動化</span>
          </h1>
          <p className="mt-6 text-lg text-gray-600 max-w-2xl mx-auto">
            職務経歴書・志望動機・自己PRをAIが自動生成。
            <br />
            日本の転職市場に特化した書類作成支援ツール。
          </p>
          <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/resume/new"
              className="bg-primary text-white px-8 py-3 rounded-lg text-lg font-semibold hover:bg-primary-dark transition-colors shadow-lg shadow-blue-200"
            >
              無料で職務経歴書を作成
            </Link>
            <Link
              href="/pricing"
              className="border-2 border-gray-300 text-gray-700 px-8 py-3 rounded-lg text-lg font-semibold hover:border-gray-400 transition-colors"
            >
              料金プランを見る
            </Link>
          </div>
          <p className="mt-4 text-sm text-gray-500">
            無料プラン: 月3回まで生成可能 / クレジットカード不要
          </p>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 px-4">
        <div className="max-w-6xl mx-auto">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-4">
            3つのAI機能で転職活動をサポート
          </h2>
          <p className="text-center text-gray-500 mb-12 max-w-2xl mx-auto">
            面倒な書類作成をAIに任せて、面接準備や企業研究に時間を使いましょう。
          </p>

          <div className="grid md:grid-cols-3 gap-8">
            {features.map((feature) => (
              <Link
                key={feature.title}
                href={feature.href}
                className="group bg-white border border-gray-200 rounded-xl p-6 hover:shadow-lg hover:border-primary/30 transition-all"
              >
                <div className="text-primary mb-4">{feature.icon}</div>
                <h3 className="text-xl font-semibold text-gray-900 mb-2 group-hover:text-primary transition-colors">
                  {feature.title}
                </h3>
                <p className="text-gray-500 text-sm leading-relaxed">
                  {feature.description}
                </p>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="bg-gray-50 py-20 px-4">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-12">
            かんたん3ステップ
          </h2>

          <div className="grid md:grid-cols-3 gap-8">
            {steps.map((s) => (
              <div key={s.step} className="text-center">
                <div className="w-12 h-12 bg-primary text-white rounded-full flex items-center justify-center text-xl font-bold mx-auto mb-4">
                  {s.step}
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">
                  {s.title}
                </h3>
                <p className="text-gray-500 text-sm">{s.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Comparison Section */}
      <section className="py-20 px-4">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl font-bold text-center text-gray-900 mb-12">
            他のサービスとの違い
          </h2>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b-2 border-gray-200">
                  <th className="py-3 px-4 text-sm font-semibold text-gray-600">
                    比較項目
                  </th>
                  <th className="py-3 px-4 text-sm font-semibold text-primary">
                    キャリアAI
                  </th>
                  <th className="py-3 px-4 text-sm font-semibold text-gray-600">
                    求人サイト内蔵ツール
                  </th>
                  <th className="py-3 px-4 text-sm font-semibold text-gray-600">
                    ChatGPT
                  </th>
                </tr>
              </thead>
              <tbody className="text-sm">
                <tr className="border-b border-gray-100">
                  <td className="py-3 px-4 font-medium text-gray-700">
                    AI活用
                  </td>
                  <td className="py-3 px-4 text-primary font-medium">
                    転職特化AI
                  </td>
                  <td className="py-3 px-4 text-gray-500">なし</td>
                  <td className="py-3 px-4 text-gray-500">汎用AI</td>
                </tr>
                <tr className="border-b border-gray-100">
                  <td className="py-3 px-4 font-medium text-gray-700">
                    日本の書式対応
                  </td>
                  <td className="py-3 px-4 text-primary font-medium">
                    完全対応
                  </td>
                  <td className="py-3 px-4 text-gray-500">テンプレのみ</td>
                  <td className="py-3 px-4 text-gray-500">プロンプト次第</td>
                </tr>
                <tr className="border-b border-gray-100">
                  <td className="py-3 px-4 font-medium text-gray-700">
                    企業別カスタマイズ
                  </td>
                  <td className="py-3 px-4 text-primary font-medium">
                    自動最適化
                  </td>
                  <td className="py-3 px-4 text-gray-500">手動</td>
                  <td className="py-3 px-4 text-gray-500">手動</td>
                </tr>
                <tr className="border-b border-gray-100">
                  <td className="py-3 px-4 font-medium text-gray-700">
                    月額料金
                  </td>
                  <td className="py-3 px-4 text-primary font-medium">
                    無料〜980円
                  </td>
                  <td className="py-3 px-4 text-gray-500">無料</td>
                  <td className="py-3 px-4 text-gray-500">3,000円</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="bg-primary py-16 px-4">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-white mb-4">
            今すぐ無料で始めましょう
          </h2>
          <p className="text-blue-100 mb-8">
            クレジットカード不要。月3回まで無料で書類を生成できます。
          </p>
          <Link
            href="/resume/new"
            className="inline-block bg-white text-primary px-8 py-3 rounded-lg text-lg font-semibold hover:bg-blue-50 transition-colors"
          >
            職務経歴書を作成する
          </Link>
        </div>
      </section>
    </div>
  );
}
