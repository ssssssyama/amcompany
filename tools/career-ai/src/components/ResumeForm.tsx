"use client";

import { useState } from "react";
import type { ResumeInput, WorkExperience } from "@/types";

interface ResumeFormProps {
  onSubmit: (input: ResumeInput) => void;
  loading: boolean;
}

const emptyExperience: WorkExperience = {
  company: "",
  position: "",
  startDate: "",
  endDate: "",
  description: "",
};

export function ResumeForm({ onSubmit, loading }: ResumeFormProps) {
  const [experiences, setExperiences] = useState<WorkExperience[]>([
    { ...emptyExperience },
  ]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [skills, setSkills] = useState("");
  const [qualifications, setQualifications] = useState("");
  const [targetCompany, setTargetCompany] = useState("");
  const [targetPosition, setTargetPosition] = useState("");
  const [jobDescription, setJobDescription] = useState("");

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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit({
      name,
      email,
      phone,
      experiences,
      skills,
      qualifications,
      targetCompany,
      targetPosition,
      jobDescription,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Basic Info */}
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">基本情報</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              氏名
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
              placeholder="山田 太郎"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              メールアドレス
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
              placeholder="taro@example.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              電話番号
            </label>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
              placeholder="090-1234-5678"
            />
          </div>
        </div>
      </div>

      {/* Work Experience */}
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">職務経歴</h2>
          <button
            type="button"
            onClick={addExperience}
            className="text-sm text-primary hover:text-primary-dark font-medium"
          >
            + 職歴を追加
          </button>
        </div>

        <div className="space-y-6">
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
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    会社名 <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={exp.company}
                    onChange={(e) =>
                      updateExperience(index, "company", e.target.value)
                    }
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
                    placeholder="株式会社サンプル"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    役職・ポジション <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={exp.position}
                    onChange={(e) =>
                      updateExperience(index, "position", e.target.value)
                    }
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
                    placeholder="Webエンジニア"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    入社年月
                  </label>
                  <input
                    type="month"
                    value={exp.startDate}
                    onChange={(e) =>
                      updateExperience(index, "startDate", e.target.value)
                    }
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    退社年月
                  </label>
                  <input
                    type="month"
                    value={exp.endDate}
                    onChange={(e) =>
                      updateExperience(index, "endDate", e.target.value)
                    }
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
                  />
                </div>
              </div>
              <div className="mt-3">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  業務内容・実績 <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={exp.description}
                  onChange={(e) =>
                    updateExperience(index, "description", e.target.value)
                  }
                  rows={4}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none resize-y"
                  placeholder="担当した業務内容、使用技術、達成した成果などを記入してください"
                  required
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Skills & Qualifications */}
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          スキル・資格
        </h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              スキル・技術
            </label>
            <textarea
              value={skills}
              onChange={(e) => setSkills(e.target.value)}
              rows={3}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none resize-y"
              placeholder="例: Python, TypeScript, React, AWS, プロジェクトマネジメント"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              資格・認定
            </label>
            <textarea
              value={qualifications}
              onChange={(e) => setQualifications(e.target.value)}
              rows={2}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none resize-y"
              placeholder="例: 基本情報技術者、TOEIC 800点、AWS Solutions Architect"
            />
          </div>
        </div>
      </div>

      {/* Target Company */}
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          応募先情報
        </h2>
        <p className="text-sm text-gray-500 mb-4">
          応募先の情報を入力すると、その企業・職種に最適化された職務経歴書を生成します。
        </p>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              応募先企業名
            </label>
            <input
              type="text"
              value={targetCompany}
              onChange={(e) => setTargetCompany(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
              placeholder="株式会社ターゲット"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              応募職種
            </label>
            <input
              type="text"
              value={targetPosition}
              onChange={(e) => setTargetPosition(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
              placeholder="バックエンドエンジニア"
            />
          </div>
        </div>
        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            求人票の内容（コピペ可）
          </label>
          <textarea
            value={jobDescription}
            onChange={(e) => setJobDescription(e.target.value)}
            rows={4}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none resize-y"
            placeholder="求人票の仕事内容、求めるスキル、歓迎条件などを貼り付けてください"
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
          "AIで職務経歴書を生成"
        )}
      </button>
    </form>
  );
}
