"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

type Workspace = { id: string; name: string };
type Subject = { id: string; name: string };
type Version = {
  id: string;
  version_number: number;
  original_filename: string;
  extraction: { status: string; character_count: number; segment_count: number; error_message: string | null } | null;
};
type Resource = { id: string; title: string; versions: Version[] };
type Citation = { document_title: string; original_filename: string; version_number: number; locator: string };
type QuestionVersion = {
  id: string;
  version_number: number;
  question_type: string;
  stem: string;
  options: { id: string; text: string }[] | null;
  marks: number;
  difficulty: string;
  cognitive_level: string;
  source_citations: Citation[];
  review_status: string;
};
type Question = { id: string; current_version_number: number; versions: QuestionVersion[] };
type GenerationResult = { created_count: number; total_marks: number; questions: Question[] };
type Exam = { id: string; title: string; duration_minutes: number; total_marks: number; question_count: number };

const panel = { background: "#11151e", border: "1px solid #293242", borderRadius: 14, padding: 18 } as const;
const field = { width: "100%", padding: "10px 12px", marginTop: 6, borderRadius: 8, border: "1px solid #364154", background: "#0b1018", color: "#f4f6fa" } as const;
const action = { border: 0, borderRadius: 8, padding: "11px 15px", background: "#ff8a35", color: "#20140b", fontWeight: 800, cursor: "pointer" } as const;
const questionTypes = ["multiple_choice", "multiple_select", "true_false", "fill_blank", "short_answer", "long_answer", "numeric", "matching", "ordering", "programming", "diagram_interpretation", "diagram_construction"];

export default function QuestionBankPage() {
  const [apiBase, setApiBase] = useState(process.env.NEXT_PUBLIC_EXAMGEN_API_URL ?? "http://localhost:8000");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [resources, setResources] = useState<Resource[]>([]);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [selectedQuestionVersions, setSelectedQuestionVersions] = useState<string[]>([]);
  const [examTitle, setExamTitle] = useState("My subject practice examination");
  const [examDuration, setExamDuration] = useState(45);
  const [exams, setExams] = useState<Exam[]>([]);
  const [questionCount, setQuestionCount] = useState(10);
  const [totalMarks, setTotalMarks] = useState(30);
  const [difficulty, setDifficulty] = useState("medium");
  const [selectedTypes, setSelectedTypes] = useState<string[]>(["multiple_choice", "short_answer"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const base = apiBase.replace(/\/$/, "");
  async function api<T>(path: string, init: RequestInit = {}, auth = token): Promise<T> {
    const response = await fetch(`${base}/api/v1${path}`, {
      ...init,
      headers: { ...(init.headers ?? {}), ...(auth ? { Authorization: `Bearer ${auth}` } : {}) },
    });
    const data = await response.json() as T & { detail?: string };
    if (!response.ok) throw new Error(data.detail ?? "The request could not be completed.");
    return data;
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
      setNotice("Signed in. Select a subject to build your private question bank.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Sign-in failed."); }
    finally { setBusy(false); }
  }

  async function chooseWorkspace(id: string) {
    setWorkspaceId(id); setSubjectId(""); setSubjects([]); setResources([]); setQuestions([]); setSelectedSources([]);
    if (!id) return;
    setBusy(true); setError("");
    try { setSubjects(await api<Subject[]>(`/workspaces/${id}/subjects`)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load subjects."); }
    finally { setBusy(false); }
  }

  async function chooseSubject(id: string) {
    setSubjectId(id); setResources([]); setQuestions([]); setSelectedSources([]);
    if (!id) return;
    setBusy(true); setError("");
    try {
      const [sourceList, bank, practiceExams] = await Promise.all([
        api<Resource[]>(`/workspaces/${workspaceId}/subjects/${id}/resources`),
        api<Question[]>(`/workspaces/${workspaceId}/subjects/${id}/questions`),
        api<Exam[]>(`/workspaces/${workspaceId}/subjects/${id}/practice-exams`),
      ]);
      setResources(sourceList); setQuestions(bank); setExams(practiceExams);
      setSelectedQuestionVersions([]);
      setNotice(`Loaded ${sourceList.length} resources, ${bank.length} questions and ${practiceExams.length} practice exams.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load this subject."); }
    finally { setBusy(false); }
  }

  function toggleSource(id: string) {
    setSelectedSources((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  function toggleType(type: string) {
    setSelectedTypes((current) => current.includes(type) ? current.filter((item) => item !== type) : [...current, type]);
  }


  function toggleQuestionVersion(id: string) {
    setSelectedQuestionVersions((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  async function createPracticeExam(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedQuestionVersions.length || !examTitle.trim()) {
      setError("Select at least one question and provide a practice examination title.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const exam = await api<Exam>(
        `/workspaces/${workspaceId}/subjects/${subjectId}/practice-exams`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: examTitle.trim(),
            duration_minutes: examDuration,
            question_version_ids: selectedQuestionVersions,
          }),
        },
      );
      setExams((current) => [exam, ...current]);
      setSelectedQuestionVersions([]);
      setNotice(`Practice examination created: ${exam.question_count} questions, ${exam.total_marks} marks, ${exam.duration_minutes} minutes.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not create the practice exam."); }
    finally { setBusy(false); }
  }
\n  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedSources.length || !selectedTypes.length) {
      setError("Select at least one fully extracted source version and one question type.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<GenerationResult>(
        `/workspaces/${workspaceId}/subjects/${subjectId}/questions/generate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_version_ids: selectedSources,
            question_count: questionCount,
            total_marks: totalMarks,
            question_types: selectedTypes,
            difficulty,
            cognitive_levels: ["remember", "understand", "apply", "analyze"],
          }),
        },
      );
      setQuestions((current) => [...result.questions, ...current]);
      setNotice(`Generated and saved ${result.created_count} source-cited questions worth ${result.total_marks} marks.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Question generation failed."); }
    finally { setBusy(false); }
  }

  return (
    <main style={{ maxWidth: 1120, margin: "0 auto", padding: "28px 18px", color: "#f4f6fa" }}>
      <header style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", borderBottom: "1px solid #293242", paddingBottom: 16 }}>
        <div><Link href="/" style={{ color: "#ff8a35", textDecoration: "none", fontWeight: 900 }}>EXAMGEN AI</Link><p style={{ color: "#9aa5b5", fontSize: 11, letterSpacing: ".12em", margin: "5px 0 0" }}>STUDENT COURSEWORK · QUESTION BANK</p></div>
        <Link href="/coursework" style={{ color: "#55d5e8", fontSize: 12 }}>My resources</Link>
      </header>
      <section style={{ margin: "25px 0" }}>
        <p style={{ color: "#ff8a35", fontSize: 11, fontWeight: 800, letterSpacing: ".15em" }}>SOURCE-GROUNDED PRACTICE</p>
        <h1 style={{ fontSize: "clamp(28px,4vw,40px)", margin: "7px 0" }}>Build your question bank</h1>
        <p style={{ color: "#9aa5b5", lineHeight: 1.6, maxWidth: 780 }}>Generate reusable practice questions from your own extracted lecture notes and coursework. Each question retains source-page citations. Model answers and explanations stay on the server and are not exposed by the question-bank listing.</p>
      </section>

      <section style={panel}>
        <h2 style={{ fontSize: 17, marginTop: 0 }}>1. Your coursework account</h2>
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
            <label style={{ fontSize: 13 }}>Subject / module<select value={subjectId} disabled={!workspaceId} onChange={(event) => void chooseSubject(event.target.value)} style={field}><option value="">Choose subject</option>{subjects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
            <button onClick={() => { setToken(""); setWorkspaces([]); setSubjects([]); setResources([]); setQuestions([]); setWorkspaceId(""); setSubjectId(""); }} style={{ ...action, alignSelf: "end", background: "#293242", color: "#f4f6fa" }}>Sign out</button>
          </div>
        )}
        {error && <p role="alert" style={{ color: "#ff9a9a" }}>{error}</p>}
        {notice && <p role="status" style={{ color: "#75d9a5" }}>{notice}</p>}
      </section>

      {token && workspaceId && subjectId && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(280px,.85fr) minmax(0,1.4fr)", gap: 16, marginTop: 16 }}>
          <section style={panel}>
            <h2 style={{ fontSize: 17, marginTop: 0 }}>2. Choose source versions</h2>
            <p style={{ color: "#9aa5b5", fontSize: 12 }}>Only fully extracted resources can be used. Private resources remain private to their uploader.</p>
            {resources.map((resource) => resource.versions.map((version) => (
              <label key={version.id} style={{ display: "flex", gap: 9, padding: 10, marginTop: 8, border: "1px solid #364154", borderRadius: 8, opacity: version.extraction?.status === "extracted" ? 1 : .55 }}>
                <input type="checkbox" checked={selectedSources.includes(version.id)} disabled={version.extraction?.status !== "extracted"} onChange={() => toggleSource(version.id)} />
                <span><strong style={{ fontSize: 13 }}>{resource.title}</strong><small style={{ display: "block", color: "#9aa5b5" }}>v{version.version_number} · {version.extraction?.status ?? "pending"} · {version.extraction?.segment_count ?? 0} segments</small></span>
              </label>
            )))}
            {resources.length === 0 && <p style={{ color: "#9aa5b5", fontSize: 13 }}>Upload and process resources in <Link href="/coursework" style={{ color: "#55d5e8" }}>My resources</Link> first.</p>}
            <h2 style={{ fontSize: 17, marginTop: 24 }}>3. Generation blueprint</h2>
            <form onSubmit={generate}>
              <label style={{ display: "block", fontSize: 13 }}>Number of questions<input type="number" min={1} max={30} value={questionCount} onChange={(event) => setQuestionCount(Number(event.target.value))} style={field} /></label>
              <label style={{ display: "block", fontSize: 13, marginTop: 10 }}>Total marks<input type="number" min={1} max={300} value={totalMarks} onChange={(event) => setTotalMarks(Number(event.target.value))} style={field} /></label>
              <label style={{ display: "block", fontSize: 13, marginTop: 10 }}>Difficulty<select value={difficulty} onChange={(event) => setDifficulty(event.target.value)} style={field}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
              <p style={{ color: "#cbd3df", fontSize: 13, marginBottom: 6 }}>Question types</p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 8 }}>
                {questionTypes.map((type) => <label key={type} style={{ fontSize: 11, color: "#cbd3df", display: "flex", gap: 6, alignItems: "center" }}><input type="checkbox" checked={selectedTypes.includes(type)} onChange={() => toggleType(type)} />{type.replaceAll("_", " ")}</label>)}
              </div>
              <button type="submit" disabled={busy || !selectedSources.length || !selectedTypes.length} style={{ ...action, width: "100%", marginTop: 16 }}>{busy ? "Generating…" : "Generate question bank"}</button>
              <p style={{ color: "#8793a5", fontSize: 11, lineHeight: 1.5 }}>AI generation is rate-limited. The provider must be configured by the platform administrator. Generated items are drafts for practice, not approved formal assessment questions.</p>
            </form>
          </section>

          <section style={panel}>
            <h2 style={{ fontSize: 17, marginTop: 0 }}>4. My reusable questions ({questions.length})</h2>
            {questions.length === 0 && <p style={{ color: "#9aa5b5", fontSize: 13 }}>Your generated questions will appear here with citations to their source material.</p>}
            {questions.map((question) => question.versions.map((version) => (
              <article key={version.id} style={{ borderTop: "1px solid #293242", padding: "14px 0" }}>
                <label style={{ display: "flex", gap: 8, alignItems: "center", color: "#55d5e8", fontSize: 12 }}>
                  <input type="checkbox" checked={selectedQuestionVersions.includes(version.id)} onChange={() => toggleQuestionVersion(version.id)} />
                  Include in a practice examination
                </label>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                  <strong style={{ fontSize: 13 }}>{version.question_type.replaceAll("_", " ")}</strong>
                  <small style={{ color: "#55d5e8" }}>{version.marks} marks · {version.difficulty} · {version.cognitive_level} · {version.review_status}</small>
                </div>
                <p style={{ lineHeight: 1.6 }}>{version.stem}</p>
                {version.options?.map((option) => <p key={option.id} style={{ color: "#cbd3df", fontSize: 13, margin: "5px 0" }}>{option.id}. {option.text}</p>)}
                <small style={{ color: "#9aa5b5" }}>Sources: {version.source_citations.map((citation) => `${citation.document_title} · ${citation.locator}`).join("; ")}</small>
              </article>
            )))}
            <div style={{ borderTop: "1px solid #293242", marginTop: 18, paddingTop: 14 }}>
              <h3 style={{ fontSize: 16 }}>5. Assemble a timed practice exam</h3>
              <form onSubmit={createPracticeExam}>
                <label style={{ display: "block", fontSize: 13 }}>Exam title<input value={examTitle} onChange={(event) => setExamTitle(event.target.value)} required maxLength={240} style={field} /></label>
                <label style={{ display: "block", fontSize: 13, marginTop: 10 }}>Duration (minutes)<input type="number" min={5} max={360} value={examDuration} onChange={(event) => setExamDuration(Number(event.target.value))} style={field} /></label>
                <p style={{ color: "#9aa5b5", fontSize: 12 }}>{selectedQuestionVersions.length} question version(s) selected. The exam freezes their current wording, marks and order.</p>
                <button type="submit" disabled={busy || !selectedQuestionVersions.length} style={{ ...action, width: "100%" }}>Create practice examination</button>
              </form>
              <h3 style={{ fontSize: 16, marginTop: 22 }}>My practice examinations ({exams.length})</h3>
              {exams.map((exam) => <div key={exam.id} style={{ padding: 12, marginTop: 8, border: "1px solid #364154", borderRadius: 8 }}>
                <strong>{exam.title}</strong>
                <small style={{ display: "block", color: "#9aa5b5", marginTop: 4 }}>{exam.question_count} questions · {exam.total_marks} marks · {exam.duration_minutes} minutes</small>
                <Link href="/coursework/practice" style={{ display: "inline-block", color: "#55d5e8", marginTop: 8, fontSize: 12 }}>Open practice exams →</Link>
              </div>)}
            </div>
          </section>
        </div>
      )}
      <footer style={{ color: "#778497", fontSize: 11, padding: "24px 0" }}>EXAMGEN AI · Generated questions remain drafts. Verify the source citations and academic accuracy before relying on them.</footer>
    </main>
  );
}
