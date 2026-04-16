"use client";

import Link from "next/link";
import { useState } from "react";

export function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <header className="bg-white border-b border-gray-200">
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16 items-center">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-2xl font-bold text-primary">
              キャリアAI
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-8">
            <Link
              href="/resume/new"
              className="text-gray-600 hover:text-gray-900 font-medium"
            >
              職務経歴書
            </Link>
            <Link
              href="/motivation"
              className="text-gray-600 hover:text-gray-900 font-medium"
            >
              志望動機
            </Link>
            <Link
              href="/review"
              className="text-gray-600 hover:text-gray-900 font-medium"
            >
              自己PR添削
            </Link>
            <Link
              href="/pricing"
              className="text-gray-600 hover:text-gray-900 font-medium"
            >
              料金プラン
            </Link>
            <Link
              href="/blog"
              className="text-gray-600 hover:text-gray-900 font-medium"
            >
              コラム
            </Link>
          </div>

          <div className="hidden md:flex items-center gap-4">
            <Link
              href="/resume/new"
              className="bg-primary text-white px-5 py-2 rounded-lg font-medium hover:bg-primary-dark transition-colors"
            >
              無料で始める
            </Link>
          </div>

          <button
            className="md:hidden p-2"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="メニュー"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              {mobileMenuOpen ? (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              ) : (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6h16M4 12h16M4 18h16"
                />
              )}
            </svg>
          </button>
        </div>

        {mobileMenuOpen && (
          <div className="md:hidden pb-4 space-y-2">
            <Link
              href="/resume/new"
              className="block px-3 py-2 text-gray-600 hover:bg-gray-50 rounded-lg"
              onClick={() => setMobileMenuOpen(false)}
            >
              職務経歴書
            </Link>
            <Link
              href="/motivation"
              className="block px-3 py-2 text-gray-600 hover:bg-gray-50 rounded-lg"
              onClick={() => setMobileMenuOpen(false)}
            >
              志望動機
            </Link>
            <Link
              href="/review"
              className="block px-3 py-2 text-gray-600 hover:bg-gray-50 rounded-lg"
              onClick={() => setMobileMenuOpen(false)}
            >
              自己PR添削
            </Link>
            <Link
              href="/pricing"
              className="block px-3 py-2 text-gray-600 hover:bg-gray-50 rounded-lg"
              onClick={() => setMobileMenuOpen(false)}
            >
              料金プラン
            </Link>
            <Link
              href="/blog"
              className="block px-3 py-2 text-gray-600 hover:bg-gray-50 rounded-lg"
              onClick={() => setMobileMenuOpen(false)}
            >
              コラム
            </Link>
            <Link
              href="/resume/new"
              className="block px-3 py-2 bg-primary text-white text-center rounded-lg font-medium"
              onClick={() => setMobileMenuOpen(false)}
            >
              無料で始める
            </Link>
          </div>
        )}
      </nav>
    </header>
  );
}
