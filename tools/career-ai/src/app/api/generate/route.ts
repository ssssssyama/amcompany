import { NextRequest, NextResponse } from "next/server";
import { generateResume, generateMotivation, reviewSelfPR } from "@/lib/ai";
import type { GenerateRequest, ResumeInput, MotivationInput, ReviewInput } from "@/types";

export async function POST(request: NextRequest) {
  try {
    const body: GenerateRequest = await request.json();

    if (!body.type || !body.input) {
      return NextResponse.json(
        { error: "type と input は必須です" },
        { status: 400 }
      );
    }

    let content: string;

    switch (body.type) {
      case "resume":
        content = await generateResume(body.input as ResumeInput);
        break;
      case "motivation":
        content = await generateMotivation(body.input as MotivationInput);
        break;
      case "review":
        content = await reviewSelfPR(body.input as ReviewInput);
        break;
      default:
        return NextResponse.json(
          { error: `不明な生成タイプ: ${body.type}` },
          { status: 400 }
        );
    }

    return NextResponse.json({ content });
  } catch (error) {
    console.error("Generation error:", error);

    if (error instanceof Error && error.message.includes("ANTHROPIC_API_KEY")) {
      return NextResponse.json(
        { error: "APIキーが設定されていません。管理者にお問い合わせください。" },
        { status: 500 }
      );
    }

    return NextResponse.json(
      { error: "生成中にエラーが発生しました。しばらくしてからもう一度お試しください。" },
      { status: 500 }
    );
  }
}
