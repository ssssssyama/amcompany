"use client";

import { useState } from "react";

interface ResultDisplayProps {
  result: string | null;
  loading: boolean;
  error: string | null;
  title: string;
}

export function ResultDisplay({
  result,
  loading,
  error,
  title,
}: ResultDisplayProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    if (!result) return;
    await navigator.clipboard.writeText(result);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handlePrint() {
    if (!result) return;
    const printWindow = window.open("", "_blank");
    if (!printWindow) return;
    printWindow.document.write(`<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<title>${title} - キャリアAI</title>
<style>
  body { font-family: "Hiragino Kaku Gothic ProN", "Yu Gothic", "Meiryo", sans-serif; padding: 40px; line-height: 1.8; color: #333; font-size: 14px; }
  h1 { font-size: 18px; border-bottom: 2px solid #333; padding-bottom: 8px; margin-bottom: 24px; }
  pre { white-space: pre-wrap; word-wrap: break-word; }
  @media print { body { padding: 20px; } }
</style>
</head>
<body>
<h1>${title}</h1>
<pre>${result.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</pre>
</body>
</html>`);
    printWindow.document.close();
    printWindow.print();
  }

  if (loading) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl p-6 h-full flex flex-col items-center justify-center min-h-[400px]">
        <div className="animate-pulse flex flex-col items-center gap-4">
          <div className="w-16 h-16 bg-primary/10 rounded-full flex items-center justify-center">
            <svg
              className="animate-spin h-8 w-8 text-primary"
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
          </div>
          <div className="text-center">
            <p className="text-gray-900 font-medium">AIが生成中...</p>
            <p className="text-gray-500 text-sm mt-1">
              最適な職務経歴書を作成しています
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white border border-red-200 rounded-xl p-6">
        <div className="flex items-center gap-2 text-red-600 mb-2">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span className="font-medium">エラー</span>
        </div>
        <p className="text-red-600 text-sm">{error}</p>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="bg-white border border-gray-200 rounded-xl p-6 h-full flex flex-col items-center justify-center min-h-[400px]">
        <div className="text-center text-gray-400">
          <svg
            className="w-16 h-16 mx-auto mb-4 opacity-50"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <p className="font-medium">生成結果がここに表示されます</p>
          <p className="text-sm mt-1">
            左のフォームに情報を入力して「生成」ボタンを押してください
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
        <div className="flex gap-2">
          <button
            onClick={handleCopy}
            className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition-colors"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
              />
            </svg>
            {copied ? "コピーしました" : "コピー"}
          </button>
          <button
            onClick={handlePrint}
            className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition-colors"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"
              />
            </svg>
            PDF保存
          </button>
        </div>
      </div>

      <div className="prose prose-sm max-w-none">
        <div className="whitespace-pre-wrap text-gray-700 text-sm leading-relaxed border border-gray-100 rounded-lg p-4 bg-gray-50 max-h-[600px] overflow-y-auto">
          {result}
        </div>
      </div>
    </div>
  );
}
