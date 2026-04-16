import type { Metadata } from "next";
import Link from "next/link";
import { getAllPosts } from "@/lib/blog";

export const metadata: Metadata = {
  title: "転職お役立ちコラム",
  description:
    "職務経歴書の書き方、志望動機のコツ、自己PRの作り方など、転職活動に役立つ情報を発信。AIを活用した最新の転職テクニックも紹介。",
};

export default function BlogPage() {
  const posts = getAllPosts();

  return (
    <div className="py-16 px-4">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-4">
            転職お役立ちコラム
          </h1>
          <p className="text-gray-500 text-lg">
            職務経歴書・志望動機・自己PRの書き方を徹底解説
          </p>
        </div>

        <div className="space-y-6">
          {posts.map((post) => (
            <Link
              key={post.slug}
              href={`/blog/${post.slug}`}
              className="block bg-white border border-gray-200 rounded-xl p-6 hover:shadow-md hover:border-primary/30 transition-all"
            >
              <div className="flex items-center gap-3 text-sm text-gray-400 mb-2">
                <time dateTime={post.date}>{post.date}</time>
                <span>|</span>
                <span>{post.readTime}で読める</span>
              </div>
              <h2 className="text-xl font-semibold text-gray-900 mb-2 group-hover:text-primary">
                {post.title}
              </h2>
              <p className="text-gray-500 text-sm leading-relaxed">
                {post.description}
              </p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
