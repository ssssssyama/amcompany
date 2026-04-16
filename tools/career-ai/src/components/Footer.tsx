import Link from "next/link";

export function Footer() {
  return (
    <footer className="bg-gray-50 border-t border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div>
            <span className="text-xl font-bold text-primary">キャリアAI</span>
            <p className="mt-2 text-sm text-gray-500">
              AIが転職活動をサポート。
              <br />
              職務経歴書・志望動機・自己PRを自動生成。
            </p>
          </div>

          <div>
            <h3 className="font-semibold text-gray-900 mb-3">機能</h3>
            <ul className="space-y-2 text-sm text-gray-500">
              <li>
                <Link href="/resume/new" className="hover:text-gray-700">
                  AI職務経歴書ジェネレーター
                </Link>
              </li>
              <li>
                <Link href="/motivation" className="hover:text-gray-700">
                  AI志望動機ジェネレーター
                </Link>
              </li>
              <li>
                <Link href="/review" className="hover:text-gray-700">
                  自己PR添削
                </Link>
              </li>
            </ul>
          </div>

          <div>
            <h3 className="font-semibold text-gray-900 mb-3">情報</h3>
            <ul className="space-y-2 text-sm text-gray-500">
              <li>
                <Link href="/pricing" className="hover:text-gray-700">
                  料金プラン
                </Link>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-8 pt-8 border-t border-gray-200 text-center text-sm text-gray-400">
          &copy; {new Date().getFullYear()} キャリアAI. All rights reserved.
        </div>
      </div>
    </footer>
  );
}
