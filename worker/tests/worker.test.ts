import { describe, it } from "node:test";
import assert from "node:assert/strict";
import worker, { type Env } from "../src/index";

const ORIGIN = "https://omendi-atlan.github.io";
const exam = {
  title: "Foundations Assessment", subject: "Computing", durationMinutes: 30, totalMarks: 5,
  instructions: ["Answer all questions."],
  questions: [
    { id: "q1", section: "A", prompt: "Select the correct option.", type: "multiple_choice", marks: 2, difficulty: "foundation", options: ["A", "B"], answer: "B", explanation: "B is correct." },
    { id: "q2", section: "B", prompt: "Explain the concept clearly.", type: "short_answer", marks: 3, difficulty: "intermediate", answer: "A model answer", explanation: "Use the rubric.", rubric: { criteria: [{ criterion: "Conceptual accuracy", marks: 3, descriptors: { full: "Accurate explanation", partial: "Partially accurate", none: "No relevant explanation" } }] } }
  ]
};
type AttemptRow = { exam_json: string; status: string; expires_at: string };
class FakeStatement {
  private values: unknown[] = [];
  constructor(private readonly db: FakeD1, private readonly sql: string) {}
  bind(...values: unknown[]) { this.values = values; return this; }
  async first<T>() { return (this.db.row as T | null) ?? null; }
  async run() {
    if (this.sql.includes("UPDATE examination_attempts")) {
      if (!this.db.row || this.db.row.status !== "in_progress") return { meta: { changes: 0 } };
      this.db.row.status = this.sql.includes("status = 'expired'") ? "expired" : "submitted";
      this.db.updated = true;
      return { meta: { changes: 1 } };
    }
    return { meta: { changes: 0 } };
  }
}
class FakeD1 {
  row: AttemptRow | null;
  updated = false;
  constructor(row: AttemptRow | null = null) { this.row = row; }
  prepare(sql: string) { return new FakeStatement(this, sql); }
}
function makeEnv(db: FakeD1): Env { return { ALLOWED_ORIGIN: ORIGIN, DB: db as unknown as Env["DB"] }; }
function request(path: string, body: unknown, origin = ORIGIN) {
  return new Request("https://worker.test" + path, { method: "POST", headers: { Origin: origin, "Content-Type": "application/json" }, body: typeof body === "string" ? body : JSON.stringify(body) });
}
const attemptId = "8f7c7f8d-48a1-4f4a-8b1e-a8f7c7f8d48a";
function seededDb(expiresAt = new Date(Date.now() + 60_000).toISOString()) {
  return new FakeD1({ exam_json: JSON.stringify(exam), status: "in_progress", expires_at: expiresAt });
}

describe("EXAMGEN AI Worker submission safeguards", () => {
  it("rejects malformed JSON", async () => {
    const r = await worker.fetch(request("/api/examinations/attempts/submit", "{"), makeEnv(seededDb()));
    assert.equal(r.status, 400);
  });
  it("rejects unapproved origins", async () => {
    const r = await worker.fetch(request("/api/examinations/attempts/submit", { attemptId, answers: {} }, "https://attacker.example"), makeEnv(seededDb()));
    assert.equal(r.status, 403);
  });
  it("marks objective answers and leaves written responses pending human review", async () => {
    const db = seededDb();
    const r = await worker.fetch(request("/api/examinations/attempts/submit", { attemptId, answers: { q1: "B", q2: "My explanation" } }), makeEnv(db));
    const payload = await r.json() as { result: { objectiveScore: number; pendingReviewCount: number; status: string; questionResults: Array<{status:string}> } };
    assert.equal(r.status, 200);
    assert.equal(payload.result.objectiveScore, 2);
    assert.equal(payload.result.pendingReviewCount, 1);
    assert.equal(payload.result.status, "provisional");
    assert.equal(payload.result.questionResults[1].status, "pending_manual_review");
    assert.equal(db.row?.status, "submitted");
  });
  it("rejects a second submission", async () => {
    const db = seededDb(); db.row!.status = "submitted";
    const r = await worker.fetch(request("/api/examinations/attempts/submit", { attemptId, answers: {} }), makeEnv(db));
    assert.equal(r.status, 409);
  });
  it("expires attempts past their deadline", async () => {
    const db = seededDb(new Date(Date.now() - 1000).toISOString());
    const r = await worker.fetch(request("/api/examinations/attempts/submit", { attemptId, answers: {} }), makeEnv(db));
    assert.equal(r.status, 410); assert.equal(db.row?.status, "expired");
  });
  it("rejects unknown question identifiers", async () => {
    const r = await worker.fetch(request("/api/examinations/attempts/submit", { attemptId, answers: { injected: "B" } }), makeEnv(seededDb()));
    assert.equal(r.status, 400);
  });
  it("does not expose deferred examiner routes", async () => {
    const r = await worker.fetch(new Request("https://worker.test/examiner", { headers: { Origin: ORIGIN } }), makeEnv(seededDb()));
    assert.equal(r.status, 404);
  });
  it("reports that no AI provider is configured or required", async () => {
    const r = await worker.fetch(new Request("https://worker.test/health"), makeEnv(seededDb()));
    assert.equal(r.status, 200);
    assert.deepEqual(await r.json(), { status: "ok", service: "examgen-ai-api", database: "configured", aiProvider: "none" });
  });
  it("supports configured numeric tolerance", async () => {
    const numericExam = { ...exam, totalMarks: 5, questions: [{ id:"n1", section:"A", prompt:"Calculate 2 + 2.", type:"numeric", marks:5, difficulty:"foundation", answer:"4", numericTolerance:0.1, explanation:"The answer is four." }] };
    const db = new FakeD1({ exam_json: JSON.stringify(numericExam), status:"in_progress", expires_at:new Date(Date.now()+60_000).toISOString() });
    const r = await worker.fetch(request("/api/examinations/attempts/submit", { attemptId, answers:{n1:"4.05"} }), makeEnv(db));
    const payload = await r.json() as {result:{objectiveScore:number}};
    assert.equal(r.status,200); assert.equal(payload.result.objectiveScore,5);
  });
});
