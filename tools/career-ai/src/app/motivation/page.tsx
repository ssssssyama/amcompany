"use client";

import { useState } from "react";
import { ResultDisplay } from "@/components/ResultDisplay";
import type { WorkExperience, MotivationInput } from "@/types";

const emptyExperience: WorkExperience = {
  company: "",
  position: "",
  startDate: "",
  endDate: "",
  description: "",
};

export default function MotivationPage() {
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [experiences, setExperiences] = useState<WorkExperience[]>([
    { ...emptyExperience },
  ]);
  const [skills, setSkills] = useState("");
  const [targetCompany, setTargetCompany] = useState("");
  const [targetPosition, setTargetPosition] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [companyInfo, setCompanyInfo] = useState("");

  function addExperience() {
    setExperiences([...experiences, { ...emptyExperience }]);
  }

  function removeExperience(index: number) {
    if (experiences.length === 1) return;
    setExperiences(experiences.filter((_, i) => i !== index));
  }

  function updateExperience(
    index: number,
    field: keyof WorkExperience,
    value: string
  ) {
    const updated = [...experiences];
    updated[index] = { ...updated[index], [field]: value };
    setExperiences(updated);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    const input: MotivationInput = {
      experiences,
      skills,
      targetCompany,
      targetPosition,
      jobDescription,
      companyInfo,
    };

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "motivation", input }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "生成に失敗しました");
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
            AI志望動機ジェネレーター
          </h1>
          <p className="mt-2 text-gray-500">
            応募先企業の情報とあなたの経歴から、カスタマイズされた志望動機を自動生成します。
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Target Company (prioritized at top) */}
            <div className="bg-white border border-gray-200 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                応募先情報
              </h2>
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    応募先企業名 <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={targetCompany}
                    onChange={(e) => setTargetCompany(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
                    placeholder="株式会社ターゲット"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    応募職種 <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={targetPosition}
                    onChange={(e) => setTargetPosition(e.target.value)}
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
                    placeholder="バックエンドエンジニア"
                    required
                  />
                </div>
              </div>
              <div className="mt-4">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  企業情報（事業内容、理念など）
                </label>
                <textarea
                  value={companyInfo}
                  onChange={(e) => setCompanyInfo(e.target.value)}
                  rows={3}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none resize-y"
                  placeholder="企業のWebサイトや採用ページの情報を貼り付けてください"
                />
              </div>
              <div className="mt-4">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  求人票の内容
                </label>
                <textarea
                  value={jobDescription}
                  onChange={(e) => setJobDescription(e.target.value)}
                  rows={3}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none resize-y"
                  placeholder="求人票の内容をコピペしてください"
                />
              </div>
            </div>

            {/* Career History */}
            <div className="bg-white border border-gray-200 rounded-xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-gray-900">
                  あなたの経歴
                </h2>
                <button
                  type="button"
                  onClick={addExperience}
                  className="text-sm text-primary hover:text-primary-dark font-medium"
                >
                  + 職歴を追加
                </button>
              </div>

              <div className="space-y-4">
                {experiences.map((exp, index) => (
                  <div
                    key={index}
                    className="border border-gray-100 rounded-lg p-4 bg-gray-50"
                  >
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-sm font-medium text-gray-500">
                        職歴 {index + 1}
                      </span>
                      {experiences.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeExperience(index)}
                          className="text-sm text-red-500 hover:text-red-700"
                        >
                          削除
                        </button>
                      )}
                    </div>
                    <div className="grid sm:grid-cols-2 gap-3">
                      <input
                        type="text"
                        value={exp.company}
                        onChange={(e) =>
                          updateExperience(index, "company", e.target.value)
                        }
                        className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
                        placeholder="会社名"
                        required
                      />
                      <input
                        type="text"
                        value={exp.position}
                        onChange={(e) =>
                          updateExperience(index, "position", e.target.value)
                        }
                        className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
                        placeholder="役職"
                        required
                      />
                    </div>
                    <textarea
                      value={exp.description}
                      onChange={(e) =>
                        updateExperience(index, "description", e.target.value)
                      }
                      rows={3}
                      className="mt-3 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none resize-y"
                      placeholder="業務内容・実績"
                      required
                    />
                  </div>
                ))}
              </div>

              <div className="mt-4">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  スキル・技術
                </label>
                <textarea
                  value={skills}
                  onChange={(e) => setSkills(e.target.value)}
                  rows={2}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none resize-y"
                  placeholder="Python, React, AWS, etc."
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
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
                  AIが生成中...
                </span>
              ) : (
                "AIで志望動機を生成"
              )}
            </button>
          </form>

          <div>
            <ResultDisplay
              result={result}
              loading={loading}
              error={error}
              title="生成された志望動機"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
