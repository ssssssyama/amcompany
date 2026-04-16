import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI職務経歴書ジェネレーター｜無料で自動作成",
  description:
    "職歴・スキル・応募先情報を入力するだけで、AIが最適化された職務経歴書を自動生成。日本の転職市場に特化した書式に完全対応。月3回まで無料。",
  openGraph: {
    title: "AI職務経歴書ジェネレーター｜キャリアAI",
    description:
      "職歴を入力するだけ。AIが応募先企業に最適化された職務経歴書を数秒で自動生成します。",
  },
};

export default function ResumeLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
