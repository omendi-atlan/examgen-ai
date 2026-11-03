import { describe, it } from "node:test";
import assert from "node:assert/strict";
import worker, { type Env } from "../src/index";

const ORIGIN = "https://omendi-atlan.github.io";
const exam = {
  title: "Foundations Assessment",
  subject: "Computing",
  durationMinutes: 30,
  totalMarks: 5,
  instructions: ["Answer all questions."],
  questions: [
    { id: "q1", section: "A", prompt: "Select the correct option.", type: "multiple_choice", marks: 2, difficulty: "foundation", options: ["A", "B"], answer: "B", explanation: "B is correct." },
    { id: "q2", section: "B", prompt: "Explain the concept clearly.", type: "short_answer", marks: 3, difficulty: "intermediate", answer: "A model answer", explanation: "Award marks for relevant reasoning." }
  ]
};

type AttemptRow = { exam_json: string; status: string; expires_at: string };
class FakeStatement {
  private values: unknown[] = [];
  constructor(private readonly db: FakeD1, private readonly sql: string) {}
  bind(...values: unknown[]) { this.values = values; return this; }
  async first<T>() { return (this.db.row as T | null) ?? null; }
  async run() {
    if (this.sql.includes("INSERT INTO examination_attempts")) {
      this.db.row = { exam_json: String(this.values[3]), status: "in_progress", expires_at: String(this.values[4]) };
      this.db.inserted = true;
      return { meta: { changes: 1 } };
    }
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
  inserted = false;
  updated = false;
  constructor(row: AttemptRow | null = null) { this.row = row; }
  prepare(sql: string) { return new FakeStatement(this, sql); }
}

function makeEnv(db: FakeD1): Env {
  return { OPENAI_API_KEY: "test-key", ALLOWED_ORIGIN: ORIGIN, DB: db as unknown as Env["DB"] };
}
function request(path: string, body: unknown, origin = ORIGIN) {
  return new Request("https://worker.test" + path, {
    method: "POST",
    headers: { Origin: origin, "Content-Type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body)
  });
}
const attemptId = "8f7c7f8d-48a1-4f4a-8b1e-a8f7c7f8d48a";
function seededDb(expiresAt = new Date(Date.now() + 60_000).toISOString()) {
  return new FakeD1({ exam_json: JSON.stringify(exam), status: "in_progress", expires_at: expiresAt });
}

describe("EXAMGEN AI Worker submission safeguards", () => {
  it("rejects malformed JSON", async () => {
    const response = await worker.fetch(request("/api/examinations/attempts/submit", "{"), makeEnv(seededDb()));
    assert.equal(response.status, 400);
  });

  it("rejects requests from unapproved origins", async () => {
    const response = await worker.fetch(request("/api/examinations/attempts/submit", { attemptId, answers: {} }, "https://attacker.example"), makeEnv(seededDb()));
    assert.equal(response.status, 403);
  });

  it("marks objective answers on the server and flags written answers for review", async () => {
    const db = seededDb();
    const response = await worker.fetch(request("/api/examinations/attempts/submit", {
      attemptId, answers: { q1: "B", q2: "My explanation" }
    }), makeEnv(db));
    const payload = await response.json() as { result: { objectiveScore: number; pendingReviewCount: number; status: string } };
    assert.equal(response.status, 200);
    assert.equal(payload.result.objectiveScore, 2);
    assert.equal(payload.result.pendingReviewCount, 1);
    assert.equal(payload.result.status, "pending_review");
    assert.equal(db.row?.status, "submitted");
  });

  it("rejects a second submission for the same attempt", async () => {
    const db = seededDb();
    db.row!.status = "submitted";
    const response = await worker.fetch(request("/api/examinations/attempts/submit", { attemptId, answers: {} }), makeEnv(db));
    assert.equal(response.status, 409);
  });

  it("expires an attempt whose deadline has passed", async () => {
    const db = seededDb(new Date(Date.now() - 1_000).toISOString());
    const response = await worker.fetch(request("/api/examinations/attempts/submit", { attemptId, answers: {} }), makeEnv(db));
    assert.equal(response.status, 410);
    assert.equal(db.row?.status, "expired");
  });

  it("rejects answer identifiers that do not belong to the examination", async () => {
    const response = await worker.fetch(request("/api/examinations/attempts/submit", { attemptId, answers: { injected_question: "B" } }), makeEnv(seededDb()));
    assert.equal(response.status, 400);
  });

  it("does not disclose answer keys from the health endpoint", async () => {
    const response = await worker.fetch(new Request("https://worker.test/health"), makeEnv(seededDb()));
    assert.equal(response.status, 200);
    const payload = await response.json() as Record<string, unknown>;
    assert.deepEqual(payload, { status: "ok", service: "examgen-ai-api", database: "configured" });
  });
});
