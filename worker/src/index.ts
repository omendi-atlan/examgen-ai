interface D1PreparedStatement {
  bind(...values: unknown[]): D1PreparedStatement;
  first<T>(): Promise<T | null>;
  run(): Promise<{ meta: { changes: number } }>;
}
interface D1Database {
  prepare(query: string): D1PreparedStatement;
}

export interface Env {
  ALLOWED_ORIGIN?: string;
  DB: D1Database;
}

type QuestionType = "multiple_choice" | "dropdown" | "short_answer" | "long_answer" | "numeric";
type Difficulty = "foundation" | "intermediate" | "advanced";
type Mode = "practice" | "simulation";
type RubricCriterion = {
  criterion: string;
  marks: number;
  descriptors: { full: string; partial: string; none: string };
};
type Question = {
  id: string;
  section: string;
  prompt: string;
  type: QuestionType;
  marks: number;
  difficulty: Difficulty;
  options?: string[];
  answer: string;
  explanation: string;
  numericTolerance?: number;
  visualDescription?: string;
  rubric?: { criteria: RubricCriterion[] };
};
type Exam = {
  title: string;
  subject: string;
  durationMinutes: number;
  totalMarks: number;
  instructions: string[];
  questions: Question[];
};
type PublicQuestion = Omit<Question, "answer" | "explanation" | "rubric">;
type PublicExam = Omit<Exam, "questions"> & { questions: PublicQuestion[] };

const QUESTION_TYPES: QuestionType[] = ["multiple_choice", "dropdown", "short_answer", "long_answer", "numeric"];
const DIFFICULTIES: Difficulty[] = ["foundation", "intermediate", "advanced"];
const HEADERS = { "Content-Type": "application/json", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
const MAX_BODY_BYTES = 65_536;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function response(body: unknown, status = 200, origin = "", allowed = ""): Response {
  const headers = new Headers(HEADERS);
  headers.set("Vary", "Origin");
  if (origin && origin === allowed) headers.set("Access-Control-Allow-Origin", origin);
  headers.set("Access-Control-Allow-Methods", "POST, OPTIONS, GET");
  headers.set("Access-Control-Allow-Headers", "Content-Type");
  return new Response(JSON.stringify(body), { status, headers });
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function publicExam(exam: Exam): PublicExam {
  return { ...exam, questions: exam.questions.map(({ answer: _a, explanation: _e, rubric: _r, ...q }) => q) };
}
function validateExam(value: unknown): value is Exam {
  if (!isRecord(value)) return false;
  if (typeof value.title !== "string" || value.title.trim().length < 3 || value.title.length > 180) return false;
  if (typeof value.subject !== "string" || value.subject.trim().length < 2 || value.subject.length > 160) return false;
  if (!Number.isInteger(value.durationMinutes) || Number(value.durationMinutes) < 1 || Number(value.durationMinutes) > 360) return false;
  if (!Number.isInteger(value.totalMarks) || Number(value.totalMarks) < 1 || Number(value.totalMarks) > 1000) return false;
  if (!Array.isArray(value.instructions) || value.instructions.length < 1 || value.instructions.length > 12 ||
      !value.instructions.every((v) => typeof v === "string" && v.trim().length > 0 && v.length <= 500)) return false;
  if (!Array.isArray(value.questions) || value.questions.length < 1 || value.questions.length > 100) return false;
  const ids = new Set<string>();
  let total = 0;
  for (const q of value.questions) {
    if (!isRecord(q) || typeof q.id !== "string" || !/^[a-zA-Z0-9_-]{1,48}$/.test(q.id) || ids.has(q.id)) return false;
    ids.add(q.id);
    if (typeof q.section !== "string" || q.section.length > 100 ||
        typeof q.prompt !== "string" || q.prompt.trim().length < 5 || q.prompt.length > 8000 ||
        !QUESTION_TYPES.includes(q.type as QuestionType) ||
        !Number.isInteger(q.marks) || Number(q.marks) < 1 || Number(q.marks) > Number(value.totalMarks) ||
        !DIFFICULTIES.includes(q.difficulty as Difficulty) ||
        typeof q.answer !== "string" || q.answer.length > 8000 ||
        typeof q.explanation !== "string" || q.explanation.length > 5000) return false;
    const objective = q.type === "multiple_choice" || q.type === "dropdown";
    if (objective) {
      if (!Array.isArray(q.options) || q.options.length < 2 || q.options.length > 10 ||
          !q.options.every((o) => typeof o === "string" && o.trim().length > 0 && o.length <= 500) ||
          new Set(q.options).size !== q.options.length || !q.options.includes(q.answer)) return false;
    } else if (q.options !== undefined) return false;
    if (q.type === "numeric") {
      if (q.answer.trim() === "" || !Number.isFinite(Number(q.answer))) return false;
      if (q.numericTolerance !== undefined &&
          (typeof q.numericTolerance !== "number" || !Number.isFinite(q.numericTolerance) || q.numericTolerance < 0 || q.numericTolerance > 1_000_000)) return false;
    } else if (q.numericTolerance !== undefined) return false;
    if (q.visualDescription !== undefined &&
        (typeof q.visualDescription !== "string" || q.visualDescription.length > 1200)) return false;
    const written = q.type === "short_answer" || q.type === "long_answer";
    if (written) {
      if (!isRecord(q.rubric) || !Array.isArray(q.rubric.criteria) || q.rubric.criteria.length < 1 || q.rubric.criteria.length > 12) return false;
      let rubricTotal = 0;
      for (const c of q.rubric.criteria) {
        if (!isRecord(c) || typeof c.criterion !== "string" || c.criterion.trim().length < 2 ||
            !Number.isInteger(c.marks) || Number(c.marks) < 1 || !isRecord(c.descriptors)) return false;
        if (!isRecord(c.descriptors)) return false;
        const descriptors = c.descriptors;
        if (!(["full", "partial", "none"] as const).every((k) => typeof descriptors[k] === "string" && String(descriptors[k]).length >= 2 && String(descriptors[k]).length <= 1000)) return false;
        rubricTotal += Number(c.marks);
      }
      if (rubricTotal !== Number(q.marks)) return false;
    } else if (q.rubric !== undefined) return false;
    total += Number(q.marks);
  }
  return total === Number(value.totalMarks);
}
function normalise(value: string): string {
  return value.trim().replace(/\\s+/g, " ").toLocaleLowerCase();
}
function markAttempt(exam: Exam, answers: Record<string, unknown>) {
  const questionResults = exam.questions.map((q) => {
    const submitted = typeof answers[q.id] === "string" ? String(answers[q.id]).slice(0, 10_000) : "";
    const objective = q.type === "multiple_choice" || q.type === "dropdown" || q.type === "numeric";
    if (!objective) return { questionId: q.id, marksAvailable: q.marks, marksAwarded: null, status: "pending_manual_review", explanation: null, rubric: q.rubric ?? null };
    const correct = q.type === "numeric"
      ? submitted.trim() !== "" && Number.isFinite(Number(submitted)) &&
        Math.abs(Number(submitted) - Number(q.answer)) <= (q.numericTolerance ?? 0)
      : normalise(submitted) === normalise(q.answer);
    return { questionId: q.id, marksAvailable: q.marks, marksAwarded: correct ? q.marks : 0,
      status: correct ? "correct" : "incorrect", explanation: q.explanation };
  });
  const auto = questionResults.filter((q) => q.marksAwarded !== null);
  const pending = questionResults.filter((q) => q.status === "pending_manual_review");
  return {
    status: pending.length ? "provisional" : "marked",
    objectiveScore: auto.reduce((n, q) => n + (q.marksAwarded ?? 0), 0),
    autoMarkTotal: auto.reduce((n, q) => n + q.marksAvailable, 0),
    totalMarks: exam.totalMarks,
    pendingReviewCount: pending.length,
    questionResults,
    writtenMarkingNote: pending.length ? "Written responses require rubric-based human assessment. No automated written mark has been assigned." : null
  };
}
async function allowGeneration(request: Request, env: Env): Promise<boolean> {
  const ip = request.headers.get("CF-Connecting-IP");
  if (!ip) return false;
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(ip));
  const hash = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  const windowStart = Math.floor(Date.now() / 600_000) * 600_000;
  await env.DB.prepare("INSERT INTO api_rate_limits (ip_hash, window_start, request_count) VALUES (?, ?, 1) ON CONFLICT(ip_hash) DO UPDATE SET request_count = CASE WHEN api_rate_limits.window_start = excluded.window_start THEN api_rate_limits.request_count + 1 ELSE 1 END, window_start = excluded.window_start")
    .bind(hash, windowStart).run();
  const row = await env.DB.prepare("SELECT request_count FROM api_rate_limits WHERE ip_hash = ?").bind(hash).first<{ request_count: number }>();
  return (row?.request_count ?? 0) <= 5;
}
async function readJson(request: Request): Promise<{ value?: unknown; error?: string }> {
  const length = Number(request.headers.get("Content-Length") ?? "0");
  if (length > MAX_BODY_BYTES) return { error: "Request is too large." };
  const raw = await request.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_BODY_BYTES) return { error: "Request is too large." };
  try { return { value: JSON.parse(raw) as unknown }; } catch { return { error: "Request body must be valid JSON." }; }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = request.headers.get("Origin") ?? "";
    const allowed = env.ALLOWED_ORIGIN ?? "https://omendi-atlan.github.io";
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      if (origin !== allowed) return response({ error: "Origin not allowed." }, 403);
      const headers = new Headers({ "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "POST, OPTIONS, GET", "Access-Control-Allow-Headers": "Content-Type", Vary: "Origin" });
      return new Response(null, { status: 204, headers });
    }
    if (url.pathname === "/health" && request.method === "GET") return response({ status: "ok", service: "examgen-ai-api", database: "configured", aiProvider: "none" }, 200, origin, allowed);
    if (origin !== allowed) return response({ error: "Origin not allowed." }, 403);
    if (url.pathname === "/api/examinations/generate" && request.method === "POST") {
      if (!await allowGeneration(request, env)) return response({ error: "Generation limit reached. Please retry later." }, 429, origin, allowed);
      const parsed = await readJson(request);
      if (parsed.error) return response({ error: parsed.error }, parsed.error.includes("large") ? 413 : 400, origin, allowed);
      if (!isRecord(parsed.value) || !["practice", "simulation"].includes(String(parsed.value.mode)) || !validateExam(parsed.value.exam)) {
        return response({ error: "Provide a valid examination with approved questions, answers, marking rubrics and matching total marks." }, 400, origin, allowed);
      }
      const exam = parsed.value.exam;
      const attemptId = crypto.randomUUID();
      const expiresAt = new Date(Date.now() + (exam.durationMinutes * 60_000) + 120_000).toISOString();
      try {
        await env.DB.prepare("INSERT INTO examination_attempts (id, mode, subject, exam_json, expires_at) VALUES (?, ?, ?, ?, ?)")
          .bind(attemptId, parsed.value.mode as Mode, exam.subject, JSON.stringify(exam), expiresAt).run();
        return response({ attemptId, expiresAt, exam: publicExam(exam) }, 201, origin, allowed);
      } catch {
        return response({ error: "The examination attempt could not be saved." }, 500, origin, allowed);
      }
    }
    if (url.pathname === "/api/examinations/attempts/submit" && request.method === "POST") {
      const parsed = await readJson(request);
      if (parsed.error) return response({ error: parsed.error }, parsed.error.includes("large") ? 413 : 400, origin, allowed);
      if (!isRecord(parsed.value) || typeof parsed.value.attemptId !== "string" || !UUID.test(parsed.value.attemptId) || !isRecord(parsed.value.answers)) {
        return response({ error: "A valid attemptId and answers object are required." }, 400, origin, allowed);
      }
      const answers = parsed.value.answers;
      if (Object.keys(answers).length > 100 || Object.values(answers).some((v) => typeof v !== "string" || v.length > 10_000)) {
        return response({ error: "Submitted answers are invalid or too large." }, 400, origin, allowed);
      }
      try {
        const row = await env.DB.prepare("SELECT exam_json, status, expires_at FROM examination_attempts WHERE id = ?")
          .bind(parsed.value.attemptId).first<{ exam_json: string; status: string; expires_at: string }>();
        if (!row) return response({ error: "Examination attempt not found." }, 404, origin, allowed);
        if (row.status !== "in_progress") return response({ error: "This examination attempt has already been submitted or closed." }, 409, origin, allowed);
        if (Date.parse(row.expires_at) <= Date.now()) {
          await env.DB.prepare("UPDATE examination_attempts SET status = 'expired' WHERE id = ? AND status = 'in_progress'").bind(parsed.value.attemptId).run();
          return response({ error: "This examination attempt has expired." }, 410, origin, allowed);
        }
        const exam = JSON.parse(row.exam_json) as Exam;
        const allowedIds = new Set(exam.questions.map((q) => q.id));
        if (Object.keys(answers).some((id) => !allowedIds.has(id))) return response({ error: "Submission contains an unknown question identifier." }, 400, origin, allowed);
        const result = markAttempt(exam, answers);
        const update = await env.DB.prepare("UPDATE examination_attempts SET status = 'submitted', submitted_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'), answers_json = ?, result_json = ? WHERE id = ? AND status = 'in_progress' AND expires_at > ?")
          .bind(JSON.stringify(answers), JSON.stringify(result), parsed.value.attemptId, new Date().toISOString()).run();
        if (update.meta.changes !== 1) return response({ error: "This attempt was already submitted or has expired." }, 409, origin, allowed);
        return response({ result }, 200, origin, allowed);
      } catch {
        return response({ error: "The examination could not be submitted. Please retry." }, 500, origin, allowed);
      }
    }
    if (url.pathname === "/api/examinations/attempts/mark-written" && request.method === "POST") {
      const parsed = await readJson(request);
      if (parsed.error) return response({ error: parsed.error }, parsed.error.includes("large") ? 413 : 400, origin, allowed);
      if (!isRecord(parsed.value) || typeof parsed.value.attemptId !== "string" || !UUID.test(parsed.value.attemptId) ||
          typeof parsed.value.questionId !== "string" || !Array.isArray(parsed.value.criteria) ||
          (parsed.value.feedback !== undefined && (typeof parsed.value.feedback !== "string" || parsed.value.feedback.length > 4000))) {
        return response({ error: "A valid attemptId, questionId, criteria array and optional feedback are required." }, 400, origin, allowed);
      }
      try {
        const row = await env.DB.prepare("SELECT exam_json, result_json, status FROM examination_attempts WHERE id = ?")
          .bind(parsed.value.attemptId).first<{ exam_json: string; result_json: string; status: string }>();
        if (!row) return response({ error: "Examination attempt not found." }, 404, origin, allowed);
        if (row.status !== "submitted") return response({ error: "Only submitted attempts can be self-assessed." }, 409, origin, allowed);
        const exam = JSON.parse(row.exam_json) as Exam;
        const questionId = String(parsed.value.questionId);
        const question = exam.questions.find((q) => q.id === questionId);
        if (!question || (question.type !== "short_answer" && question.type !== "long_answer") || !question.rubric) {
          return response({ error: "The selected question does not have a written-answer rubric." }, 400, origin, allowed);
        }
        if (parsed.value.criteria.length !== question.rubric.criteria.length) return response({ error: "Every rubric criterion must receive a mark." }, 400, origin, allowed);
        const criteriaResults: Array<{criterion:string;marksAvailable:number;marksAwarded:number;descriptor:string}> = [];
        for (let i = 0; i < question.rubric.criteria.length; i++) {
          const submitted = parsed.value.criteria[i];
          const criterion = question.rubric.criteria[i];
          if (!isRecord(submitted) || !Number.isInteger(submitted.marksAwarded) ||
              Number(submitted.marksAwarded) < 0 || Number(submitted.marksAwarded) > criterion.marks) {
            return response({ error: "A rubric mark is outside its permitted range." }, 400, origin, allowed);
          }
          criteriaResults.push({ criterion: criterion.criterion, marksAvailable: criterion.marks,
            marksAwarded: Number(submitted.marksAwarded), descriptor: Number(submitted.marksAwarded) === criterion.marks ? criterion.descriptors.full : Number(submitted.marksAwarded) === 0 ? criterion.descriptors.none : criterion.descriptors.partial });
        }
        const result = JSON.parse(row.result_json) as Record<string, unknown>;
        const questionResults = Array.isArray(result.questionResults) ? result.questionResults as Array<Record<string, unknown>> : [];
        const target = questionResults.find((item) => item.questionId === question.id);
        if (!target) return response({ error: "The submitted question result could not be found." }, 409, origin, allowed);
        const marksAwarded = criteriaResults.reduce((sum, item) => sum + item.marksAwarded, 0);
        Object.assign(target, { marksAwarded, status: "self_assessed", criteriaResults });
        const pendingReviewCount = questionResults.filter((item) => item.status === "pending_manual_review").length;
        const writtenSelfAssessmentScore = questionResults.filter((item) => item.status === "self_assessed")
          .reduce((sum, item) => sum + Number(item.marksAwarded ?? 0), 0);
        Object.assign(result, { pendingReviewCount, writtenSelfAssessmentScore, status: pendingReviewCount ? "provisional" : "self_assessed" });
        await env.DB.prepare("UPDATE examination_attempts SET result_json = ? WHERE id = ? AND status = 'submitted'")
          .bind(JSON.stringify(result), parsed.value.attemptId).run();
        await env.DB.prepare("INSERT INTO marking_reviews (id, attempt_id, question_id, status, marks_awarded, marks_available, criteria_results_json, feedback, marker_label) VALUES (?, ?, ?, 'in_progress', ?, ?, ?, ?, 'Self-assessment (not examiner-approved)') ON CONFLICT(attempt_id, question_id) DO UPDATE SET status = 'in_progress', marks_awarded = excluded.marks_awarded, criteria_results_json = excluded.criteria_results_json, feedback = excluded.feedback, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')")
          .bind(crypto.randomUUID(), parsed.value.attemptId, question.id, marksAwarded, question.marks, JSON.stringify(criteriaResults), String(parsed.value.feedback ?? "")).run();
        return response({ result, note: "Self-assessment is for personal learning and is not an examiner-approved final mark." }, 200, origin, allowed);
      } catch {
        return response({ error: "The written response could not be self-assessed. Please retry." }, 500, origin, allowed);
      }
    }
    return response({ error: "Not found." }, 404, origin, allowed);
  }
};
