import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "料金プラン｜無料から始められる",
  description:
    "キャリアAIの料金プラン。無料プランは月3回まで生成可能。スタンダード月980円で無制限、プレミアム月1,980円で添削機能付き。",
  openGraph: {
    title: "料金プラン｜キャリアAI",
    description:
      "無料プランは月3回まで。スタンダード月980円で無制限生成。転職成功への投資対効果は抜群。",
  },
};

export default function PricingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
