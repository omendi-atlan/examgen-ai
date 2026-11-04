"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

type Workspace = { id: string; name: string };
type Subject = { id: string; name: string };
type Exam = { id: string; title: string; duration_minutes: number; total_marks: number; question_count: number };
type AttemptQuestion = {
  exam_question_id: string;
  question_version_id: string;
  ordinal: number;
  question_type: string;
  stem: string;
  options: { id: string; text: string }[] | null;
  marks: number;
  response?: Record<string, unknown>;
  marking_status: string;
  awarded_marks?: number;
  is_correct?: boolean;
  correct_answer?: Record<string, unknown>;
  explanation?: string;
};
type Attempt = {
  id: string;
  exam_id: string;
  exam_title: string;
  status: "in_progress" | "submitted" | "expired";
  started_at: string;
  expires_at: string;
  submitted_at?: string;
  total_marks: number;
  awarded_marks: number;
  pending_review_count: number;
  questions: AttemptQuestion[];
};

const panel = { background: "#11151e", border: "1px solid #293242", borderRadius: 14, padding: 18 } as const;
const field = { width: "100%", padding: "10px 12px", marginTop: 6, borderRadius: 8, border: "1px solid #364154", background: "#0b1018", color: "#f4f6fa" } as const;
const action = { border: 0, borderRadius: 8, padding: "10px 14px", background: "#ff8a35", color: "#20140b", fontWeight: 800, cursor: "pointer" } as const;

export default function PracticeExamsPage() {
  const [apiBase, setApiBase] = useState(process.env.NEXT_PUBLIC_EXAMGEN_API_URL ?? "http://localhost:8000");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [exams, setExams] = useState<Exam[]>([]);
  const [selectedExamId, setSelectedExamId] = useState("");
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [activeAttempt, setActiveAttempt] = useState<Attempt | null>(null);
  const [responses, setResponses] = useState<Record<string, Record<string, unknown>>>({});
  const [dirty, setDirty] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saveStatus, setSaveStatus] = useState("No unsaved changes");
  const [now, setNow] = useState(Date.now());
  const responsesRef = useRef(responses);

  const base = apiBase.replace(/\/$/, "");
  const api = useCallback(async <T,>(path: string, init: RequestInit = {}, auth = token): Promise<T> => {
    const response = await fetch(`${base}/api/v1${path}`, {
      ...init,
      headers: { ...(init.headers ?? {}), ...(auth ? { Authorization: `Bearer ${auth}` } : {}) },
    });
    const data = await response.json() as T & { detail?: string };
    if (!response.ok) throw new Error(data.detail ?? "The request could not be completed.");
    return data;
  }, [base, token]);

  useEffect(() => { responsesRef.current = responses; }, [responses]);

  useEffect(() => {
    if (!activeAttempt || activeAttempt.status !== "in_progress") return;
    const tick = () => setNow(Date.now());
    tick();
    const interval = window.setInterval(tick, 1000);
    return () => window.clearInterval(interval);
  }, [activeAttempt?.id, activeAttempt?.status, activeAttempt?.expires_at]);

  useEffect(() => {
    if (!activeAttempt || activeAttempt.status !== "in_progress" || dirty.length === 0) return;
    const pending = [...dirty];
    const snapshot = Object.fromEntries(pending.map((id) => [id, responses[id] ?? {}]));
    setSaveStatus("Saving responses…");
    const timeout = window.setTimeout(async () => {
      try {
        for (const examQuestionId of pending) {
          await api(
            `/workspaces/${workspaceId}/subjects/${subjectId}/practice-attempts/${activeAttempt.id}/responses/${examQuestionId}`,
            { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ response: snapshot[examQuestionId] }) },
          );
        }
        setDirty((current) => current.filter((id) =>
          !pending.includes(id) || JSON.stringify(responsesRef.current[id] ?? {}) !== JSON.stringify(snapshot[id]),
        ));
        setSaveStatus("All responses saved");
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : "Autosave failed.";
        setError(message);
        if (message.toLowerCase().includes("expired")) {
          try {
            const finalised = await api<Attempt>(`/workspaces/${workspaceId}/subjects/${subjectId}/practice-attempts/${activeAttempt.id}`);
            activateAttempt(finalised);
            setNotice("The server timer expired and your attempt was finalised.");
          } catch { /* Keep the original autosave error visible. */ }
        }
      }
    }, 650);
    return () => window.clearTimeout(timeout);
  }, [activeAttempt?.id, activeAttempt?.status, dirty, responses, api, workspaceId, subjectId]);

  function activateAttempt(attempt: Attempt) {
    setActiveAttempt(attempt);
    setResponses(Object.fromEntries(attempt.questions.map((question) => [question.exam_question_id, question.response ?? {}])));
    setDirty([]);
    setSaveStatus(attempt.status === "in_progress" ? "All responses saved" : "Attempt finalised");
    setError("");
  }

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const response = await fetch(`${base}/api/v1/auth/login`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json() as { access_token?: string; detail?: string };
      if (!response.ok || !data.access_token) throw new Error(data.detail ?? "Sign-in failed.");
      const signedInToken = data.access_token;
      const available = await api<Workspace[]>("/workspaces", {}, signedInToken);
      setToken(signedInToken); setWorkspaces(available); setPassword("");
      setNotice("Signed in. Select your subject and a practice examination.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Sign-in failed."); }
    finally { setBusy(false); }
  }

  async function chooseWorkspace(id: string) {
    setWorkspaceId(id); setSubjectId(""); setSubjects([]); setExams([]); setAttempts([]); setActiveAttempt(null);
    if (!id) return;
    setBusy(true); setError("");
    try { setSubjects(await api<Subject[]>(`/workspaces/${id}/subjects`)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load subjects."); }
    finally { setBusy(false); }
  }

  async function chooseSubject(id: string) {
    setSubjectId(id); setExams([]); setAttempts([]); setActiveAttempt(null); setSelectedExamId("");
    if (!id) return;
    setBusy(true); setError("");
    try { setExams(await api<Exam[]>(`/workspaces/${workspaceId}/subjects/${id}/practice-exams`)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load practice exams."); }
    finally { setBusy(false); }
  }

  async function chooseExam(id: string) {
    setSelectedExamId(id); setAttempts([]); setActiveAttempt(null);
    if (!id) return;
    setBusy(true); setError("");
    try { setAttempts(await api<Attempt[]>(`/workspaces/${workspaceId}/subjects/${subjectId}/practice-exams/${id}/attempts`)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load attempt history."); }
    finally { setBusy(false); }
  }

  async function startAttempt() {
    if (!selectedExamId) return;
    setBusy(true); setError("");
    try {
      const attempt = await api<Attempt>(
        `/workspaces/${workspaceId}/subjects/${subjectId}/practice-exams/${selectedExamId}/attempts`,
        { method: "POST" },
      );
      activateAttempt(attempt);
      setNotice("Your timed practice attempt has started. The server controls the deadline.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not start this attempt."); }
    finally { setBusy(false); }
  }

  async function resumeAttempt(attemptId: string) {
    setBusy(true); setError("");
    try {
      const attempt = await api<Attempt>(`/workspaces/${workspaceId}/subjects/${subjectId}/practice-attempts/${attemptId}`);
      activateAttempt(attempt);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not open this attempt."); }
    finally { setBusy(false); }
  }

  function updateResponse(questionId: string, response: Record<string, unknown>) {
    setResponses((current) => ({ ...current, [questionId]: response }));
    setDirty((current) => current.includes(questionId) ? current : [...current, questionId]);
    setSaveStatus("Changes pending autosave…");
  }

  async function submitAttempt() {
    if (!activeAttempt) return;
    setBusy(true); setError("");
    const pendingAnswers = [...dirty];
    setDirty([]);
    try {
      // Flush all pending answers before final submission.
      for (const questionId of pendingAnswers) {
        await api(
          `/workspaces/${workspaceId}/subjects/${subjectId}/practice-attempts/${activeAttempt.id}/responses/${questionId}`,
          { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ response: responses[questionId] ?? {} }) },
        );
      }
      const result = await api<Attempt>(
        `/workspaces/${workspaceId}/subjects/${subjectId}/practice-attempts/${activeAttempt.id}/submit`,
        { method: "POST" },
      );
      activateAttempt(result);
      setAttempts((current) => [result, ...current.filter((item) => item.id !== result.id)]);
      setNotice(result.status === "expired" ? "The server deadline had passed. Your attempt was finalised." : "Attempt submitted. Review your objective score and answer explanations.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not submit this attempt."); }
    finally { setBusy(false); }
  }

  const remainingSeconds = activeAttempt?.status === "in_progress"
    ? Math.max(0, Math.floor((Date.parse(activeAttempt.expires_at) - now) / 1000))
    : 0;
  const timerText = `${Math.floor(remainingSeconds / 60).toString().padStart(2, "0")}:${(remainingSeconds % 60).toString().padStart(2, "0")}`;

  function renderResponse(question: AttemptQuestion) {
    const response = responses[question.exam_question_id] ?? {};
    const disabled = activeAttempt?.status !== "in_progress" || busy;
    if (["multiple_choice", "true_false"].includes(question.question_type)) {
      return <div style={{ display: "grid", gap: 8, marginTop: 12 }}>{(question.options ?? []).map((option) => (
        <label key={option.id} style={{ display: "flex", gap: 8, alignItems: "center", color: "#cbd3df" }}>
          <input type="radio" name={question.exam_question_id} disabled={disabled} checked={response.option_id === option.id} onChange={() => updateResponse(question.exam_question_id, { option_id: option.id })} />
          {option.id}. {option.text}
        </label>
      ))}</div>;
    }
    if (question.question_type === "multiple_select") {
      const selected = Array.isArray(response.option_ids) ? response.option_ids as string[] : [];
      return <div style={{ display: "grid", gap: 8, marginTop: 12 }}>{(question.options ?? []).map((option) => (
        <label key={option.id} style={{ display: "flex", gap: 8, alignItems: "center", color: "#cbd3df" }}>
          <input type="checkbox" disabled={disabled} checked={selected.includes(option.id)} onChange={(event) => updateResponse(question.exam_question_id, { option_ids: event.target.checked ? [...selected, option.id] : selected.filter((id) => id !== option.id) })} />
          {option.id}. {option.text}
        </label>
      ))}</div>;
    }
    if (question.question_type === "numeric") {
      return <label style={{ display: "block", marginTop: 12, fontSize: 13 }}>Your numeric answer<input type="number" disabled={disabled} value={typeof response.value === "number" ? response.value : ""} onChange={(event) => updateResponse(question.exam_question_id, event.target.value === "" ? {} : { value: Number(event.target.value) })} style={field} /></label>;
    }
    if (question.question_type === "fill_blank") {
      return <label style={{ display: "block", marginTop: 12, fontSize: 13 }}>Your answer<input disabled={disabled} value={typeof response.text === "string" ? response.text : ""} onChange={(event) => updateResponse(question.exam_question_id, { text: event.target.value })} style={field} /></label>;
    }
    return <label style={{ display: "block", marginTop: 12, fontSize: 13 }}>Your response<textarea disabled={disabled} rows={question.question_type === "long_answer" ? 8 : 4} value={typeof response.text === "string" ? response.text : ""} onChange={(event) => updateResponse(question.exam_question_id, { text: event.target.value })} style={field} /></label>;
  }

  return (
    <main style={{ maxWidth: 1120, margin: "0 auto", padding: "28px 18px", color: "#f4f6fa" }}>
      <header style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", borderBottom: "1px solid #293242", paddingBottom: 16 }}>
        <div><Link href="/" style={{ color: "#ff8a35", textDecoration: "none", fontWeight: 900 }}>EXAMGEN AI</Link><p style={{ color: "#9aa5b5", fontSize: 11, letterSpacing: ".12em", margin: "5px 0 0" }}>STUDENT COURSEWORK · PRACTICE EXAMINATIONS</p></div>
        <Link href="/coursework/questions" style={{ color: "#55d5e8", fontSize: 12 }}>Question bank</Link>
      </header>
      <section style={{ margin: "25px 0" }}>
        <p style={{ color: "#ff8a35", fontSize: 11, fontWeight: 800, letterSpacing: ".15em" }}>TIMED PRACTICE</p>
        <h1 style={{ fontSize: "clamp(28px,4vw,40px)", margin: "7px 0" }}>Practice examinations</h1>
        <p style={{ color: "#9aa5b5", lineHeight: 1.6, maxWidth: 780 }}>Attempt a private examination assembled from your question bank. Responses autosave, the server controls the deadline, and answer keys are released only after submission.</p>
      </section>

      <section style={panel}>
        <h2 style={{ fontSize: 17, marginTop: 0 }}>1. Select your subject and exam</h2>
        <label style={{ display: "block", fontSize: 13 }}>Python API URL<input value={apiBase} onChange={(event) => setApiBase(event.target.value)} style={field} /></label>
        {!token ? (
          <form onSubmit={signIn} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 12, alignItems: "end", marginTop: 12 }}>
            <label style={{ fontSize: 13 }}>Email<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} style={field} /></label>
            <label style={{ fontSize: 13 }}>Password<input type="password" required value={password} onChange={(event) => setPassword(event.target.value)} style={field} /></label>
            <button disabled={busy} style={action}>{busy ? "Signing in…" : "Sign in"}</button>
          </form>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12, marginTop: 12 }}>
            <label style={{ fontSize: 13 }}>Workspace<select value={workspaceId} onChange={(event) => void chooseWorkspace(event.target.value)} style={field}><option value="">Choose workspace</option>{workspaces.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label style={{ fontSize: 13 }}>Subject<select value={subjectId} disabled={!workspaceId} onChange={(event) => void chooseSubject(event.target.value)} style={field}><option value="">Choose subject</option>{subjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <label style={{ fontSize: 13 }}>Practice exam<select value={selectedExamId} disabled={!subjectId} onChange={(event) => void chooseExam(event.target.value)} style={field}><option value="">Choose exam</option>{exams.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.total_marks} marks</option>)}</select></label>
          </div>
        )}
        {error && <p role="alert" style={{ color: "#ff9a9a" }}>{error}</p>}
        {notice && <p role="status" style={{ color: "#75d9a5" }}>{notice}</p>}
      </section>

      {token && selectedExamId && (
        <section style={{ ...panel, marginTop: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 17, margin: 0 }}>2. Attempt history</h2>
            <button disabled={busy || !!activeAttempt && activeAttempt.status === "in_progress"} onClick={() => void startAttempt()} style={action}>Start new attempt</button>
          </div>
          {attempts.map((attempt) => <div key={attempt.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap", borderTop: "1px solid #293242", padding: "10px 0" }}>
            <span><strong style={{ fontSize: 13 }}>{attempt.status.replaceAll("_", " ")}</strong><small style={{ display: "block", color: "#9aa5b5" }}>{new Date(attempt.started_at).toLocaleString()} · {attempt.awarded_marks}/{attempt.total_marks} marks</small></span>
            <button disabled={busy} onClick={() => void resumeAttempt(attempt.id)} style={{ ...action, background: "#293242", color: "#f4f6fa" }}>{attempt.status === "in_progress" ? "Resume" : "Review"}</button>
          </div>)}
          {attempts.length === 0 && <p style={{ color: "#9aa5b5", fontSize: 13 }}>No attempts yet. Start one when you are ready.</p>}
        </section>
      )}

      {activeAttempt && (
        <section style={{ ...panel, marginTop: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, borderBottom: "1px solid #293242", paddingBottom: 14 }}>
            <div><p style={{ color: "#ff8a35", fontSize: 11, letterSpacing: ".12em", margin: 0 }}>PRACTICE SESSION</p><h2 style={{ margin: "5px 0", fontSize: 20 }}>{activeAttempt.exam_title}</h2></div>
            {activeAttempt.status === "in_progress" ? <div aria-live="polite" style={{ textAlign: "right" }}><strong style={{ fontSize: 26, fontVariantNumeric: "tabular-nums", color: remainingSeconds < 300 ? "#ff9a9a" : "#55d5e8" }}>{timerText}</strong><small style={{ display: "block", color: "#9aa5b5" }}>Time remaining</small></div> : <span style={{ color: "#75d9a5" }}>Attempt {activeAttempt.status}</span>}
          </div>
          <p style={{ color: "#9aa5b5", fontSize: 12 }}>{activeAttempt.questions.length} questions · {activeAttempt.total_marks} marks · Autosave: {saveStatus}</p>
          {activeAttempt.status === "in_progress" && remainingSeconds === 0 && <p role="alert" style={{ color: "#ffb18b" }}>The deadline has passed. Submit or refresh to let the server finalise your attempt.</p>}
          {activeAttempt.questions.map((question) => <article key={question.exam_question_id} style={{ borderTop: "1px solid #293242", padding: "16px 0" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><strong>Question {question.ordinal}</strong><small style={{ color: "#55d5e8" }}>{question.marks} marks · {question.question_type.replaceAll("_", " ")}</small></div>
            <p style={{ lineHeight: 1.65 }}>{question.stem}</p>
            {renderResponse(question)}
            {activeAttempt.status !== "in_progress" && <div style={{ background: "#0b1018", borderRadius: 8, padding: 12, marginTop: 12 }}>
              <p style={{ color: "#75d9a5", fontSize: 12, marginTop: 0 }}>Marking: {question.marking_status}{question.awarded_marks !== undefined ? ` · ${question.awarded_marks}/${question.marks} marks` : ""}</p>
              {question.correct_answer && <pre style={{ whiteSpace: "pre-wrap", color: "#cbd3df", fontSize: 12 }}>Model answer: {JSON.stringify(question.correct_answer, null, 2)}</pre>}
              {question.explanation && <p style={{ color: "#cbd3df", fontSize: 13 }}>Explanation: {question.explanation}</p>}
            </div>}
          </article>)}
          {activeAttempt.status === "in_progress" ? (
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, borderTop: "1px solid #293242", paddingTop: 16 }}>
              <small style={{ color: "#9aa5b5" }}>Responses autosave after a short pause. The server enforces the expiry time.</small>
              <button disabled={busy} onClick={() => void submitAttempt()} style={action}>{busy ? "Submitting…" : "Submit examination"}</button>
            </div>
          ) : (
            <p style={{ color: "#75d9a5" }}>Final score: {activeAttempt.awarded_marks}/{activeAttempt.total_marks}. {activeAttempt.pending_review_count} written response(s) require further marking.</p>
          )}
        </section>
      )}
      <footer style={{ color: "#778497", fontSize: 11, padding: "24px 0" }}>EXAMGEN AI · This is a practice simulation. Server time is authoritative; browser timers are display aids. Subjective responses are not automatically awarded marks.</footer>
    </main>
  );
}
