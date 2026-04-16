"use client";

import { useState } from "react";
import { ResultDisplay } from "@/components/ResultDisplay";

export default function ReviewPage() {
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [type, setType] = useState<"self_pr" | "motivation">("self_pr");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "review", input: { text, type } }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "添削に失敗しました");
      }

      const data = await res.json();
      setResult(data.content);
    } catch (err) {
      setError(err instanceof Error ? err.message : "エラーが発生しました");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="py-8 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl md:text-3xl font-bold text-gray-900">
            AI自己PR添削
          </h1>
          <p className="mt-2 text-gray-500">
            あなたの自己PRや志望動機をAIが添削。改善ポイントの指摘と改善版の提案を行います。
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="bg-white border border-gray-200 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                添削する文章
              </h2>

              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  文章の種類
                </label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="type"
                      value="self_pr"
                      checked={type === "self_pr"}
                      onChange={() => setType("self_pr")}
                      className="text-primary focus:ring-primary"
                    />
                    <span className="text-sm text-gray-700">自己PR</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="type"
                      value="motivation"
                      checked={type === "motivation"}
                      onChange={() => setType("motivation")}
                      className="text-primary focus:ring-primary"
                    />
                    <span className="text-sm text-gray-700">志望動機</span>
                  </label>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {type === "self_pr" ? "自己PR" : "志望動機"}の文章{" "}
                  <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={12}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none resize-y"
                  placeholder={
                    type === "self_pr"
                      ? "あなたの自己PR文を入力してください。\n\n例: 私の強みは課題解決力です。前職では..."
                      : "あなたの志望動機を入力してください。\n\n例: 貴社を志望した理由は..."
                  }
                  required
                />
                <p className="mt-1 text-xs text-gray-400">
                  {text.length} 文字
                </p>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || text.trim().length < 10}
              className="w-full bg-primary text-white py-3 rounded-lg font-semibold text-lg hover:bg-primary-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg
                    className="animate-spin h-5 w-5"
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
                  AIが添削中...
                </span>
              ) : (
                "AIで添削する"
              )}
            </button>
          </form>

          <div>
            <ResultDisplay
              result={result}
              loading={loading}
              error={error}
              title="添削結果"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
