import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { env } from "cloudflare:test";
import worker from "../../src/index";

const ORIGIN = "https://omendi-atlan.github.io";
const future = () => new Date(Date.now() + 60_000).toISOString();
const exam = {
  title: "Rate limit assessment", subject: "Computing", durationMinutes: 30, totalMarks: 5,
  instructions: ["Answer all questions."],
  questions: [{ id:"R1", section:"A", prompt:"Choose the correct option.", type:"multiple_choice", marks:5, difficulty:"foundation", options:["A","B","C","D"], answer:"B", explanation:"B is correct." }]
};
const writtenExam = {
  title: "Integration assessment", subject: "Project Management", durationMinutes: 30, totalMarks: 3,
  instructions: ["Answer all questions."],
  questions: [
    { id:"Q1", section:"A", prompt:"Choose the correct option.", type:"multiple_choice", marks:1, difficulty:"foundation", options:["A","B"], answer:"B", explanation:"B is correct." },
    { id:"Q2", section:"A", prompt:"Explain the concept in your own words.", type:"short_answer", marks:2, difficulty:"intermediate", answer:"A model answer.", explanation:"Award credit for the key concept.", rubric:{criteria:[{criterion:"Conceptual accuracy",marks:2,descriptors:{full:"Accurate",partial:"Partly accurate",none:"Incorrect"}}]} }
  ]
};
async function seedAttempt(id, status = "in_progress", expiresAt = future()) {
  await env.DB.prepare("INSERT INTO examination_attempts (id, mode, subject, exam_json, status, expires_at) VALUES (?, ?, ?, ?, ?, ?)")
    .bind(id, "practice", writtenExam.subject, JSON.stringify(writtenExam), status, expiresAt).run();
}
async function submit(id, answers) {
  return worker.fetch(new Request("https://examgen-ai-api.test/api/examinations/attempts/submit", {
    method:"POST", headers:{Origin:ORIGIN,"Content-Type":"application/json"}, body:JSON.stringify({attemptId:id,answers})
  }), env);
}
function generateRequest(ip) {
  return worker.fetch(new Request("https://examgen-ai-api.test/api/examinations/generate", {
    method:"POST", headers:{Origin:ORIGIN,"Content-Type":"application/json","CF-Connecting-IP":ip},
    body:JSON.stringify({mode:"practice",exam})
  }), env);
}
beforeAll(async () => {
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS examination_attempts (
    id TEXT PRIMARY KEY, mode TEXT NOT NULL CHECK (mode IN ('practice','simulation')), subject TEXT NOT NULL,
    exam_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress','submitted','expired')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), expires_at TEXT NOT NULL,
    submitted_at TEXT, answers_json TEXT, result_json TEXT
  )`).run();
  await env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_attempts_status_expiry ON examination_attempts(status,expires_at)").run();
  await env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_attempts_created ON examination_attempts(created_at)").run();
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS api_rate_limits (ip_hash TEXT PRIMARY KEY, window_start INTEGER NOT NULL, request_count INTEGER NOT NULL)`).run();
  await env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_api_rate_limits_window ON api_rate_limits(window_start)").run();
});
beforeEach(async () => {
  await env.DB.prepare("DELETE FROM examination_attempts").run();
  await env.DB.prepare("DELETE FROM api_rate_limits").run();
});
describe("Cloudflare Worker + D1 integration", () => {
  it("serves provider-independent health status", async () => {
    const r = await worker.fetch(new Request("https://examgen-ai-api.test/health",{headers:{Origin:ORIGIN}}),env);
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({status:"ok",database:"configured",aiProvider:"none"});
  });
  it("rejects generation when the client IP header is missing", async () => {
    const r = await worker.fetch(new Request("https://examgen-ai-api.test/api/examinations/generate",{
      method:"POST",headers:{Origin:ORIGIN,"Content-Type":"application/json"},body:JSON.stringify({mode:"practice",exam})
    }),env);
    expect(r.status).toBe(429);
    expect((await env.DB.prepare("SELECT COUNT(*) AS count FROM api_rate_limits").first()).count).toBe(0);
  });
  it("allows five exam creations per IP, blocks the sixth and resets after a new window", async () => {
    for(let i=0;i<5;i++){
      const r=await generateRequest("198.51.100.77");
      expect(r.status).toBe(201);
      const payload=await r.json();
      expect(payload.exam.questions[0]).not.toHaveProperty("answer");
      expect(payload.exam.questions[0]).not.toHaveProperty("explanation");
      expect(payload.exam.questions[0]).not.toHaveProperty("rubric");
    }
    expect((await generateRequest("198.51.100.77")).status).toBe(429);
    expect((await env.DB.prepare("SELECT request_count FROM api_rate_limits").first()).request_count).toBe(6);
    expect((await env.DB.prepare("SELECT COUNT(*) AS count FROM examination_attempts").first()).count).toBe(5);
    await env.DB.prepare("UPDATE api_rate_limits SET window_start = 0").run();
    expect((await generateRequest("198.51.100.77")).status).toBe(201);
    expect((await env.DB.prepare("SELECT request_count FROM api_rate_limits").first()).request_count).toBe(1);
  });
  it("persists a submission and leaves written responses pending manual marking", async () => {
    const id="7f8c4b2a-4b6a-4c1e-9f21-123456789abc";
    await seedAttempt(id);
    const r=await submit(id,{Q1:"B",Q2:"My explanation"});
    expect(r.status).toBe(200);
    expect(await r.json()).toMatchObject({result:{status:"provisional",objectiveScore:1,autoMarkTotal:1,pendingReviewCount:1}});
    const row=await env.DB.prepare("SELECT status,answers_json,result_json,submitted_at FROM examination_attempts WHERE id = ?").bind(id).first();
    expect(row.status).toBe("submitted");
    expect(JSON.parse(row.answers_json)).toEqual({Q1:"B",Q2:"My explanation"});
    expect(JSON.parse(row.result_json).questionResults[1].status).toBe("pending_manual_review");
    expect(row.submitted_at).toBeTruthy();
  });
  it("rejects a second submission", async () => {
    const id="8f8c4b2a-4b6a-4c1e-9f21-123456789abc";
    await seedAttempt(id);
    expect((await submit(id,{Q1:"B"})).status).toBe(200);
    expect((await submit(id,{Q1:"A"})).status).toBe(409);
  });
  it("rejects expired attempts", async () => {
    const id="9f8c4b2a-4b6a-4c1e-9f21-123456789abc";
    await seedAttempt(id,"in_progress",new Date(Date.now()-60_000).toISOString());
    expect((await submit(id,{Q1:"B"})).status).toBe(410);
    const row=await env.DB.prepare("SELECT status FROM examination_attempts WHERE id = ?").bind(id).first();
    expect(row.status).toBe("expired");
  });
});
