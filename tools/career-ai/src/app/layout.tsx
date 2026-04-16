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

export const metadata: Metadata = {
  title: "キャリアAI - AI職務経歴書・志望動機ジェネレーター",
  description:
    "AIが転職活動をサポート。職務経歴書、志望動機、自己PRをAIが自動生成・添削。日本の転職市場に特化した書類作成支援ツール。",
  keywords: [
    "職務経歴書",
    "転職",
    "AI",
    "志望動機",
    "自己PR",
    "書類作成",
    "転職活動",
  ],
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
