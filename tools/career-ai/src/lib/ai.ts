import type { ResumeInput, MotivationInput, ReviewInput } from "@/types";

const ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages";

async function callClaude(systemPrompt: string, userMessage: string): Promise<string> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    throw new Error("ANTHROPIC_API_KEY is not configured");
  }

  const model = process.env.ANTHROPIC_MODEL || "claude-sonnet-4-20250514";

  const response = await fetch(ANTHROPIC_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model,
      max_tokens: 4096,
      system: systemPrompt,
      messages: [{ role: "user", content: userMessage }],
    }),
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`Claude API error: ${response.status} - ${error}`);
  }

  const data = await response.json();
  const textBlock = data.content.find(
    (block: { type: string }) => block.type === "text"
  );
  return textBlock?.text || "";
}

export async function generateResume(input: ResumeInput): Promise<string> {
  const systemPrompt = `あなたは日本の転職市場に精通したプロのキャリアコンサルタントです。
ユーザーの職歴・スキル情報と応募先情報をもとに、日本の転職市場で通用する高品質な職務経歴書を作成してください。

以下のルールに従ってください:
1. 日本の標準的な職務経歴書フォーマットに準拠すること
2. 「〜を担当」のような受動的な表現を避け、「〜を推進し、〜を達成」のような実績ベースの記述にすること
3. 可能であれば数値（売上、人数、期間等）を含めること
4. 応募先企業・職種に関連するスキルや経験を優先的に強調すること
5. 業界で一般的なアクションワードを適切に使用すること
6. 構成は「職務要約」「職務経歴」「スキル」「資格」のセクションに分けること
7. 出力はプレーンテキスト形式で、各セクションを明確に区切ること`;

  const experienceText = input.experiences
    .map(
      (exp, i) =>
        `【職歴${i + 1}】
会社名: ${exp.company}
役職: ${exp.position}
期間: ${exp.startDate || "未記入"} 〜 ${exp.endDate || "現在"}
業務内容: ${exp.description}`
    )
    .join("\n\n");

  const userMessage = `以下の情報をもとに職務経歴書を作成してください。

■ 基本情報
氏名: ${input.name || "未記入"}

■ 職務経歴
${experienceText}

■ スキル・技術
${input.skills || "未記入"}

■ 資格
${input.qualifications || "未記入"}

■ 応募先情報
企業名: ${input.targetCompany || "未指定"}
応募職種: ${input.targetPosition || "未指定"}
求人内容: ${input.jobDescription || "未指定"}`;

  return callClaude(systemPrompt, userMessage);
}

export async function generateMotivation(input: MotivationInput): Promise<string> {
  const systemPrompt = `あなたは日本の転職市場に精通したプロのキャリアコンサルタントです。
ユーザーの経歴と応募先企業の情報をもとに、説得力のある志望動機を作成してください。

以下のルールに従ってください:
1. 「使い回し感」のない、その企業に特化した内容にすること
2. 自分の経験・スキルと企業の求める人材像を結びつけること
3. その企業・業界への関心が自然に伝わる文章にすること
4. 300〜500文字程度の長さにすること
5. 抽象的な表現（「貴社の理念に共感し」等）は具体的なエピソードで補強すること
6. 出力はプレーンテキスト形式にすること`;

  const experienceText = input.experiences
    .map(
      (exp, i) =>
        `【職歴${i + 1}】 ${exp.company} / ${exp.position}: ${exp.description}`
    )
    .join("\n");

  const userMessage = `以下の情報をもとに志望動機を作成してください。

■ 職務経歴
${experienceText}

■ スキル
${input.skills || "未記入"}

■ 応募先情報
企業名: ${input.targetCompany}
応募職種: ${input.targetPosition}
求人内容: ${input.jobDescription || "未指定"}
企業情報: ${input.companyInfo || "未指定"}`;

  return callClaude(systemPrompt, userMessage);
}

export async function reviewSelfPR(input: ReviewInput): Promise<string> {
  const typeLabel = input.type === "self_pr" ? "自己PR" : "志望動機";

  const systemPrompt = `あなたは日本の転職市場に精通したプロのキャリアコンサルタントです。
ユーザーが書いた${typeLabel}を添削し、改善提案を行ってください。

以下の観点でレビューしてください:
1. 具体性: 抽象的な表現がないか、エピソードや数値で補強できないか
2. 構成: 論理的な流れになっているか
3. 強み: 自分の強みが十分にアピールできているか
4. 説得力: 読み手（採用担当者）を納得させられる内容か
5. 文体: ビジネス文書として適切な表現か
6. 長さ: 適切な長さか

出力形式:
1. まず全体の評価（良い点と改善点）を簡潔にまとめる
2. 具体的な改善提案を箇条書きで列挙する
3. 最後に改善版の${typeLabel}を提示する`;

  const userMessage = `以下の${typeLabel}を添削してください。

${input.text}`;

  return callClaude(systemPrompt, userMessage);
}
