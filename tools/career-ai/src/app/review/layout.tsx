import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI自己PR添削｜改善ポイントを的確に指摘",
  description:
    "あなたの自己PR・志望動機をAIが添削。具体性の不足、数値化できる実績の見落としなど改善ポイントを指摘し、改善版を提案します。",
  openGraph: {
    title: "AI自己PR添削｜キャリアAI",
    description:
      "自己PRや志望動機をAIが添削。改善ポイントの指摘と改善版を提案します。",
  },
};

export default function ReviewLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
