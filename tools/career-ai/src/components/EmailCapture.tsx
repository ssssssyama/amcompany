"use client";

import { useState } from "react";

export function EmailCapture() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // TODO: Send to email service (Resend, Mailgun, etc.)
    setSubmitted(true);
  }

  if (submitted) {
    return (
      <div className="text-center py-4">
        <p className="text-primary font-semibold">
          登録ありがとうございます！
        </p>
        <p className="text-sm text-gray-500 mt-1">
          転職に役立つ情報をお届けします。
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3">
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="メールアドレスを入力"
        required
        className="flex-1 border border-gray-300 rounded-lg px-4 py-2.5 text-sm focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none"
      />
      <button
        type="submit"
        className="bg-primary text-white px-6 py-2.5 rounded-lg font-semibold hover:bg-primary-dark transition-colors whitespace-nowrap"
      >
        無料で受け取る
      </button>
    </form>
  );
}
