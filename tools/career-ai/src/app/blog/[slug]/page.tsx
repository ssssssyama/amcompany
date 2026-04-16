import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getPost, getAllPosts } from "@/lib/blog";

type Props = {
  params: Promise<{ slug: string }>;
};

export async function generateStaticParams() {
  return getAllPosts().map((post) => ({ slug: post.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const post = getPost(slug);
  if (!post) return {};

  return {
    title: post.title,
    description: post.description,
    openGraph: {
      title: post.title,
      description: post.description,
      type: "article",
      publishedTime: post.date,
    },
  };
}

export default async function BlogPostPage({ params }: Props) {
  const { slug } = await params;
  const post = getPost(slug);
  if (!post) notFound();

  return (
    <article className="py-16 px-4">
      <div className="max-w-3xl mx-auto">
        <div className="mb-8">
          <Link
            href="/blog"
            className="text-sm text-primary hover:text-primary-dark mb-4 inline-block"
          >
            &larr; コラム一覧に戻る
          </Link>
          <div className="flex items-center gap-3 text-sm text-gray-400 mb-3">
            <time dateTime={post.date}>{post.date}</time>
            <span>|</span>
            <span>{post.readTime}で読める</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-bold text-gray-900 leading-tight">
            {post.title}
          </h1>
        </div>

        <div className="prose prose-gray max-w-none">
          {post.content.split("\n").map((line, i) => {
            if (line.startsWith("## ")) {
              return (
                <h2
                  key={i}
                  className="text-xl font-bold text-gray-900 mt-10 mb-4 pb-2 border-b border-gray-200"
                >
                  {line.replace("## ", "")}
                </h2>
              );
            }
            if (line.startsWith("### ")) {
              return (
                <h3
                  key={i}
                  className="text-lg font-semibold text-gray-900 mt-6 mb-3"
                >
                  {line.replace("### ", "")}
                </h3>
              );
            }
            if (line.startsWith("---")) {
              return <hr key={i} className="my-8 border-gray-200" />;
            }
            if (line.startsWith("> ")) {
              return (
                <blockquote
                  key={i}
                  className="border-l-4 border-primary/30 pl-4 py-2 my-4 text-gray-600 bg-blue-50/50 rounded-r-lg"
                >
                  {line.replace("> ", "")}
                </blockquote>
              );
            }
            if (line.startsWith("| ")) {
              return null; // Skip table rows (rendered separately)
            }
            if (line.startsWith("- ")) {
              return (
                <li key={i} className="text-gray-600 ml-4 text-sm leading-relaxed">
                  {line.replace("- ", "")}
                </li>
              );
            }
            if (line.trim() === "") {
              return <div key={i} className="h-2" />;
            }
            // Handle bold text
            const parts = line.split(/(\*\*[^*]+\*\*)/g);
            return (
              <p key={i} className="text-gray-600 text-sm leading-relaxed">
                {parts.map((part, j) =>
                  part.startsWith("**") && part.endsWith("**") ? (
                    <strong key={j} className="text-gray-900 font-semibold">
                      {part.slice(2, -2)}
                    </strong>
                  ) : (
                    part
                  )
                )}
              </p>
            );
          })}
        </div>

        {/* CTA Section */}
        <div className="mt-12 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl p-8 text-center">
          <h3 className="text-xl font-bold text-gray-900 mb-2">
            AIで転職書類を自動作成しませんか？
          </h3>
          <p className="text-gray-500 mb-6">
            職務経歴書・志望動機をAIが数秒で生成。月3回まで無料。
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/resume/new"
              className="bg-primary text-white px-6 py-2.5 rounded-lg font-semibold hover:bg-primary-dark transition-colors"
            >
              職務経歴書を作成する
            </Link>
            <Link
              href="/motivation"
              className="border border-gray-300 text-gray-700 px-6 py-2.5 rounded-lg font-semibold hover:border-gray-400 transition-colors"
            >
              志望動機を作成する
            </Link>
          </div>
        </div>
      </div>
    </article>
  );
}
