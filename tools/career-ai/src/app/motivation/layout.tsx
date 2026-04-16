import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI志望動機ジェネレーター｜企業別にカスタマイズ",
  description:
    "応募先企業の情報とあなたの経歴から、AIが説得力のある志望動機を自動生成。使い回し感のない、企業ごとにカスタマイズされた志望動機を作成。",
  openGraph: {
    title: "AI志望動機ジェネレーター｜キャリアAI",
    description:
      "企業情報と経歴を入力するだけ。AIが応募先に合わせた志望動機を自動作成します。",
  },
};

export default function MotivationLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
