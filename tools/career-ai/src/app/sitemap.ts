import type { MetadataRoute } from "next";

const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL || "https://career-ai.example.com";

export default function sitemap(): MetadataRoute.Sitemap {
  const staticPages = [
    { url: siteUrl, lastModified: new Date(), changeFrequency: "weekly" as const, priority: 1 },
    { url: `${siteUrl}/resume/new`, lastModified: new Date(), changeFrequency: "weekly" as const, priority: 0.9 },
    { url: `${siteUrl}/motivation`, lastModified: new Date(), changeFrequency: "weekly" as const, priority: 0.8 },
    { url: `${siteUrl}/review`, lastModified: new Date(), changeFrequency: "weekly" as const, priority: 0.8 },
    { url: `${siteUrl}/pricing`, lastModified: new Date(), changeFrequency: "monthly" as const, priority: 0.7 },
  ];

  const blogPosts = [
    { slug: "how-to-write-resume", lastModified: new Date("2026-04-16") },
    { slug: "ai-resume-tools-comparison", lastModified: new Date("2026-04-16") },
    { slug: "motivation-letter-tips", lastModified: new Date("2026-04-16") },
  ];

  const blogPages = blogPosts.map((post) => ({
    url: `${siteUrl}/blog/${post.slug}`,
    lastModified: post.lastModified,
    changeFrequency: "monthly" as const,
    priority: 0.6,
  }));

  return [...staticPages, ...blogPages];
}
