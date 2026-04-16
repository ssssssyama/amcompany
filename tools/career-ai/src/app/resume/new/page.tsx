"use client";

import { useState } from "react";
import { ResumeForm } from "@/components/ResumeForm";
import { ResultDisplay } from "@/components/ResultDisplay";
import type { ResumeInput } from "@/types";

export default function NewResumePage() {
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGenerate(input: ResumeInput) {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "resume", input }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "生成に失敗しました");
      }

      const data = await res.json();
      setResult(data.content);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "エラーが発生しました"
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="py-8 px-4">
      <div className="max-w-6xl mx-auto">
        <div className="mb-8">
          <h1 className="text-2xl md:text-3xl font-bold text-gray-900">
            AI職務経歴書ジェネレーター
          </h1>
          <p className="mt-2 text-gray-500">
            職歴・スキルと応募先情報を入力すると、AIが最適化された職務経歴書を自動生成します。
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-8">
          <div>
            <ResumeForm onSubmit={handleGenerate} loading={loading} />
          </div>
          <div>
            <ResultDisplay
              result={result}
              loading={loading}
              error={error}
              title="生成された職務経歴書"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
