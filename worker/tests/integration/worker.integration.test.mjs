import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { env, SELF } from "cloudflare:test";

const ORIGIN = "https://omendi-atlan.github.io";
const future = () => new Date(Date.now() + 60_000).toISOString();
const exam = {
  title: "Integration assessment", subject: "Project Management", durationMinutes: 30,
  totalMarks: 3, instructions: ["Answer all questions."], questions: [
    { id: "Q1", section: "A", prompt: "Choose the correct option.", type: "multiple_choice", marks: 1, difficulty: "foundation", options: ["A", "B"], answer: "B", explanation: "B is correct." },
    { id: "Q2", section: "A", prompt: "Explain the concept in your own words.", type: "short_answer", marks: 2, difficulty: "intermediate", answer: "A model answer.", explanation: "Award credit for the key concept." }
  ]
};

async function seedAttempt(id, status = "in_progress", expiresAt = future()) {
  await env.DB.prepare(
    "INSERT INTO examination_attempts (id, mode, subject, exam_json, status, expires_at) VALUES (?, ?, ?, ?, ?, ?)"
  ).bind(id, "practice", exam.subject, JSON.stringify(exam), status, expiresAt).run();
}

async function submit(id, answers) {
  return SELF.fetch("https://examgen-ai-api.test/api/examinations/attempts/submit", {
    method: "POST", headers: { Origin: ORIGIN, "Content-Type": "application/json" },
    body: JSON.stringify({ attemptId: id, answers })
  });
}

beforeAll(async () => {
  // The Workers test pool creates an isolated D1 database. Initialise its
  // schema here; production schema deployment remains handled by Wrangler.
  await env.DB.prepare(`
    CREATE TABLE IF NOT EXISTS examination_attempts (
      id TEXT PRIMARY KEY,
      mode TEXT NOT NULL CHECK (mode IN ('practice', 'simulation')),
      subject TEXT NOT NULL,
      exam_json TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'in_progress'
        CHECK (status IN ('in_progress', 'submitted', 'expired')),
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
      expires_at TEXT NOT NULL,
      submitted_at TEXT,
      answers_json TEXT,
      result_json TEXT
    )
  `).run();
  await env.DB.prepare(
    "CREATE INDEX IF NOT EXISTS idx_attempts_status_expiry ON examination_attempts(status, expires_at)"
  ).run();
  await env.DB.prepare(
    "CREATE INDEX IF NOT EXISTS idx_attempts_created ON examination_attempts(created_at)"
  ).run();
});

beforeEach(async () => {
  await env.DB.prepare("DELETE FROM examination_attempts").run();
});

describe("Cloudflare Worker + D1 integration", () => {
  it("serves health from the Workers runtime", async () => {
    const response = await SELF.fetch("https://examgen-ai-api.test/health", { headers: { Origin: ORIGIN } });
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ status: "ok", database: "configured" });
  });

  it("persists a submitted attempt and returns objective marking plus written review status", async () => {
    const id = "7f8c4b2a-4b6a-4c1e-9f21-123456789abc";
    await seedAttempt(id);
    const response = await submit(id, { Q1: "B", Q2: "My explanation" });
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ result: {
      status: "pending_review", objectiveScore: 1, autoMarkTotal: 1, pendingReviewCount: 1
    }});
    const row = await env.DB.prepare(
      "SELECT status, answers_json, result_json, submitted_at FROM examination_attempts WHERE id = ?"
    ).bind(id).first();
    expect(row.status).toBe("submitted");
    expect(JSON.parse(row.answers_json)).toEqual({ Q1: "B", Q2: "My explanation" });
    expect(JSON.parse(row.result_json).objectiveScore).toBe(1);
    expect(row.submitted_at).toBeTruthy();
  });

  it("rejects a second submission after the D1 status transition", async () => {
    const id = "8f8c4b2a-4b6a-4c1e-9f21-123456789abc";
    await seedAttempt(id);
    expect((await submit(id, { Q1: "B" })).status).toBe(200);
    expect((await submit(id, { Q1: "A" })).status).toBe(409);
  });

  it("rejects expired attempts using the D1 expiry value", async () => {
    const id = "9f8c4b2a-4b6a-4c1e-9f21-123456789abc";
    await seedAttempt(id, "in_progress", new Date(Date.now() - 60_000).toISOString());
    expect((await submit(id, { Q1: "B" })).status).toBe(410);
    const row = await env.DB.prepare("SELECT status FROM examination_attempts WHERE id = ?").bind(id).first();
    expect(row.status).toBe("expired");
  });
});
