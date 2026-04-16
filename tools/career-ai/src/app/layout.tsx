import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://career-ai.example.com";

export const metadata: Metadata = {
  title: {
    default: "キャリアAI - AI職務経歴書・志望動機ジェネレーター",
    template: "%s | キャリアAI",
  },
  description:
    "AIが転職活動をサポート。職務経歴書、志望動機、自己PRをAIが自動生成・添削。日本の転職市場に特化した書類作成支援ツール。月3回まで無料。",
  keywords: [
    "職務経歴書",
    "転職",
    "AI",
    "志望動機",
    "自己PR",
    "書類作成",
    "転職活動",
    "職務経歴書 書き方",
    "職務経歴書 テンプレート",
  ],
  openGraph: {
    type: "website",
    locale: "ja_JP",
    url: siteUrl,
    siteName: "キャリアAI",
    title: "キャリアAI - AI職務経歴書・志望動機ジェネレーター",
    description:
      "AIが転職書類を自動生成。職務経歴書・志望動機・自己PRを応募先企業に最適化。無料で始められます。",
  },
  twitter: {
    card: "summary_large_image",
    title: "キャリアAI - AI職務経歴書・志望動機ジェネレーター",
    description:
      "AIが転職書類を自動生成。職務経歴書・志望動機・自己PRを応募先企業に最適化。",
  },
  robots: {
    index: true,
    follow: true,
  },
  alternates: {
    canonical: siteUrl,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="ja"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <Header />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
