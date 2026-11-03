export interface Env {
  OPENAI_API_KEY: string;
  OPENAI_MODEL?: string;
  ALLOWED_ORIGIN?: string;
}

const corsHeaders = (origin: string, allowed: string) => ({
  "Access-Control-Allow-Origin": origin === allowed ? origin : "null",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Vary": "Origin",
});

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = request.headers.get("Origin") ?? "";
    const allowed = env.ALLOWED_ORIGIN ?? "https://omendi-atlan.github.io";
    const headers = corsHeaders(origin, allowed);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers });
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...headers, "Content-Type": "application/json", "Cache-Control": "no-store" } });
    if (origin !== allowed) return json({ error: "Origin not allowed." }, 403);
    if (new URL(request.url).pathname !== "/api/examinations/generate" || request.method !== "POST") return json({ error: "Not found." }, 404);
    if (!env.OPENAI_API_KEY) return json({ error: "AI service is not configured." }, 503);
    try {
      const input = await request.json() as Record<string, unknown>;
      const subject = typeof input.subject === "string" ? input.subject.trim() : "";
      const topics = Array.isArray(input.topics) ? input.topics.filter((x): x is string => typeof x === "string").slice(0, 20) : [];
      const totalMarks = Number(input.totalMarks), durationMinutes = Number(input.durationMinutes);
      const mode = input.mode === "simulation" ? "simulation" : input.mode === "practice" ? "practice" : null;
      const difficulty = ["balanced", "foundation", "challenging", "advanced"].includes(String(input.difficulty)) ? String(input.difficulty) : null;
      if (subject.length < 2 || subject.length > 160 || !topics.length || totalMarks < 5 || totalMarks > 200 || !Number.isInteger(totalMarks) || durationMinutes < 10 || durationMinutes > 240 || !Number.isInteger(durationMinutes) || !mode || !difficulty) return json({ error: "Invalid examination configuration." }, 400);
      const visualRequirements = input.visualRequirements === true;
      const prompt = `Create a rigorous, fair ${subject} assessment for topics: ${topics.join(", ")}. Mode: ${mode}. Difficulty: ${difficulty}. Duration: ${durationMinutes} minutes. Total marks: exactly ${totalMarks}. Return JSON with title, subject, durationMinutes, totalMarks, instructions (array), and questions (array). Each question: id, section, prompt, type (multiple_choice|dropdown|short_answer|long_answer|numeric), marks (positive integer), difficulty (foundation|intermediate|advanced), options (four choices for objective questions), answer, explanation. Written questions omit options. Marks must sum exactly to ${totalMarks}. ${visualRequirements ? "If an essential visual is needed, annotate the prompt [VISUAL REQUIRED: description]; do not claim an image was generated." : "Avoid requiring visuals unless essential."}`;
      const upstream = await fetch("https://api.openai.com/v1/chat/completions", {
        method: "POST", headers: { "Authorization": `Bearer ${env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({ model: env.OPENAI_MODEL ?? "gpt-4o-mini", temperature: 0.35, response_format: { type: "json_object" }, messages: [{ role: "system", content: "You are an academic assessment designer. Return valid JSON only. Do not claim to predict a real examination." }, { role: "user", content: prompt }] }),
      });
      if (!upstream.ok) return json({ error: "The AI provider could not complete the request." }, 502);
      const payload = await upstream.json() as { choices?: { message?: { content?: string } }[] };
      const raw = payload.choices?.[0]?.message?.content;
      if (!raw) return json({ error: "The AI provider returned an empty response." }, 502);
      const exam = JSON.parse(raw) as { questions?: { marks?: number; answer?: string; explanation?: string; type?: string }[]; totalMarks?: number };
      const questions = exam.questions ?? [];
      if (!questions.length || questions.length > 30 || questions.reduce((sum, q) => sum + Number(q.marks ?? 0), 0) !== totalMarks || Number(exam.totalMarks) !== totalMarks) return json({ error: "Generated assessment failed validation. Please retry." }, 422);
      // Simulation answer keys are not sent to the browser. Server-side marking and persistent exam sessions are a later milestone.
      if (mode === "simulation") for (const q of questions) { delete q.answer; delete q.explanation; }
      return json({ exam });
    } catch {
      return json({ error: "Request could not be processed. Check the configuration and retry." }, 400);
    }
  },
};
