"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

type Workspace = { id: string; name: string; slug: string };
type Subject = { id: string; name: string; description: string | null };
type Extraction = { status: string; character_count: number; segment_count: number; error_message: string | null };
type ResourceVersion = {
  id: string;
  version_number: number;
  original_filename: string;
  extraction: Extraction | null;
};
type Resource = {
  id: string;
  title: string;
  visibility: "private" | "cohort";
  versions: ResourceVersion[];
};
type Blueprint = {
  blueprint_id: string;
  blueprint_version_id: string;
  subject_id: string;
  title: string;
  duration_minutes: number;
  total_marks: number;
  question_count: number;
  cognitive_distribution: Record<string, number>;
  difficulty_distribution: Record<string, number>;
  question_type_distribution: Record<string, number>;
};
type Citation = { id: string; source_segment_id: string; source_version_id: string; source_locator: string; excerpt: string | null };
type QuestionVersion = {
  id: string;
  version_number: number;
  topic_id: string;
  learning_outcome_id: string;
  question_type: string;
  prompt: string;
  marks: number;
  cognitive_level: string;
  difficulty: string;
  response_schema: Record<string, unknown>;
  status: string;
  citations: Citation[];
};
type Question = {
  id: string;
  subject_id: string;
  visibility: string;
  current_version_number: number;
  versions: QuestionVersion[];
};
type GenerationResult = {
  blueprint_version_id: string;
  generated_count: number;
  total_marks: number;
  questions: Question[];
};

const panel = { background: "#11151e", border: "1px solid #293242", borderRadius: 14, padding: 18 } as const;
const field = { width: "100%", padding: "11px 12px", marginTop: 6, borderRadius: 8, border: "1px solid #364154", background: "#0b1018", color: "#f4f6fa" } as const;
const action = { border: 0, borderRadius: 8, padding: "11px 15px", background: "#ff8a35", color: "#20140b", fontWeight: 800, cursor: "pointer" } as const;

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
  const [blueprints, setBlueprints] = useState<Blueprint[]>([]);
  const [blueprintVersionId, setBlueprintVersionId] = useState("");
  const [selectedSourceVersions, setSelectedSourceVersions] = useState<string[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
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
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(`${base}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json() as { access_token?: string; detail?: string };
      if (!response.ok || !data.access_token) throw new Error(data.detail ?? "Sign-in failed.");
      const signedInToken = data.access_token;
      const available = await api<Workspace[]>("/workspaces", {}, signedInToken);
      setToken(signedInToken); setWorkspaces(available); setPassword("");
      setNotice(available.length ? "Signed in. Choose a subject to build your practice question bank." : "Signed in, but no coursework workspace is assigned.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed.");
    } finally { setBusy(false); }
  }

  async function chooseWorkspace(id: string) {
    setWorkspaceId(id); setSubjectId(""); setSubjects([]); setResources([]); setBlueprints([]); setQuestions([]);
    setSelectedSourceVersions([]); setBlueprintVersionId("");
    if (!id) return;
    setBusy(true); setError("");
    try {
      const result = await api<Subject[]>(`/workspaces/${id}/subjects`);
      setSubjects(result);
      if (!result.length) setNotice("No subjects are assigned to this workspace.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load subjects."); }
    finally { setBusy(false); }
  }

  async function chooseSubject(id: string) {
    setSubjectId(id); setResources([]); setBlueprints([]); setQuestions([]);
    setSelectedSourceVersions([]); setBlueprintVersionId("");
    if (!id) return;
    setBusy(true); setError("");
    try {
      const [resourceItems, blueprintItems, questionItems] = await Promise.all([
        api<Resource[]>(`/workspaces/${workspaceId}/subjects/${id}/resources`),
        api<Blueprint[]>(`/workspaces/${workspaceId}/subjects/${id}/approved-blueprints`),
        api<Question[]>(`/workspaces/${workspaceId}/questions?subject_id=${id}`),
      ]);
      setResources(resourceItems);
      setBlueprints(blueprintItems);
      setQuestions(questionItems);
      if (blueprintItems.length) setBlueprintVersionId(blueprintItems[0].blueprint_version_id);
      setNotice(`Loaded ${resourceItems.length} resource(s), ${blueprintItems.length} approved blueprint(s) and ${questionItems.length} question(s).`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load subject question-bank data."); }
    finally { setBusy(false); }
  }

  function toggleSource(id: string, checked: boolean) {
    setSelectedSourceVersions((current) => checked
      ? [...current.filter((item) => item !== id), id]
      : current.filter((item) => item !== id));
  }

  async function generateQuestions() {
    const blueprint = blueprints.find((item) => item.blueprint_version_id === blueprintVersionId);
    if (!blueprint || selectedSourceVersions.length === 0) {
      setError("Choose an approved blueprint and at least one fully extracted resource version.");
      return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await api<GenerationResult>(
        `/workspaces/${workspaceId}/blueprints/${blueprint.blueprint_id}/versions/${blueprint.blueprint_version_id}/generate-questions`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source_version_ids: selectedSourceVersions }),
        },
      );
      setQuestions((current) => [...result.questions, ...current.filter((item) => !result.questions.some((newItem) => newItem.id === item.id))]);
      setNotice(`Generated ${result.generated_count} private draft question(s), totalling ${result.total_marks} marks. Answer keys remain protected.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Question generation failed."); }
    finally { setBusy(false); }
  }

  const selectedBlueprint = blueprints.find((item) => item.blueprint_version_id === blueprintVersionId);

  return (
    <main style={{ maxWidth: 1120, margin: "0 auto", padding: "28px 18px", color: "#f4f6fa" }}>
      <header style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", borderBottom: "1px solid #293242", paddingBottom: 16 }}>
        <div><Link href="/" style={{ color: "#ff8a35", textDecoration: "none", fontWeight: 900 }}>EXAMGEN AI</Link><p style={{ color: "#9aa5b5", fontSize: 11, letterSpacing: ".12em", margin: "5px 0 0" }}>QUESTION BANK · STUDY WORKSPACE</p></div>
        <span style={{ color: "#55d5e8", fontSize: 12 }}>{token ? "STUDENT SESSION" : "SIGN IN REQUIRED"}</span>
      </header>

      <section style={{ margin: "25px 0" }}>
        <p style={{ color: "#ff8a35", fontSize: 11, fontWeight: 800, letterSpacing: ".15em" }}>SOURCE-ALIGNED PRACTICE</p>
        <h1 style={{ fontSize: "clamp(28px,4vw,40px)", margin: "7px 0" }}>Build your question bank</h1>
        <p style={{ color: "#9aa5b5", lineHeight: 1.6, maxWidth: 780 }}>Generate questions from your own successfully extracted coursework resources using an approved examination blueprint. Every draft retains source citations. Answer keys and marking rubrics are kept server-side.</p>
      </section>

      <section style={{ ...panel, marginBottom: 16 }}>
        <h2 style={{ fontSize: 17, marginTop: 0 }}>1. Your coursework account</h2>
        <label style={{ display: "block", fontSize: 13, color: "#cbd3df" }}>Python API URL<input value={apiBase} onChange={(event) => setApiBase(event.target.value)} style={field} /></label>
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
            <button onClick={() => { setToken(""); setWorkspaces([]); setSubjects([]); setWorkspaceId(""); setSubjectId(""); setResources([]); setBlueprints([]); setQuestions([]); setSelectedSourceVersions([]); }} style={{ ...action, alignSelf: "end", background: "#293242", color: "#f4f6fa" }}>Sign out</button>
          </div>
        )}
        {error && <p role="alert" style={{ color: "#ff9a9a" }}>{error}</p>}
        {notice && <p role="status" style={{ color: "#75d9a5" }}>{notice}</p>}
      </section>

      {token && workspaceId && subjectId && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(280px,.9fr) minmax(0,1.2fr)", gap: 16 }}>
          <section style={panel}>
            <h2 style={{ fontSize: 17, marginTop: 0 }}>2. Select blueprint and sources</h2>
            <label style={{ display: "block", fontSize: 13 }}>Approved examination blueprint
              <select value={blueprintVersionId} onChange={(event) => setBlueprintVersionId(event.target.value)} style={field}>
                <option value="">Choose approved blueprint</option>
                {blueprints.map((item) => <option key={item.blueprint_version_id} value={item.blueprint_version_id}>{item.title} · {item.total_marks} marks</option>)}
              </select>
            </label>
            {selectedBlueprint && <p style={{ color: "#9aa5b5", fontSize: 12 }}>{selectedBlueprint.question_count} questions · {selectedBlueprint.total_marks} marks · {selectedBlueprint.duration_minutes} minutes</p>}
            <h3 style={{ fontSize: 15, marginTop: 22 }}>Extracted coursework sources</h3>
            <p style={{ color: "#8793a5", fontSize: 12 }}>Only resources with completed extraction can be used for generation.</p>
            {resources.map((resource) => resource.versions.filter((version) => version.extraction?.status === "extracted").map((version) => (
              <label key={version.id} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: 11, marginTop: 8, borderRadius: 9, border: "1px solid #364154", background: "#0b1018", cursor: "pointer" }}>
                <input type="checkbox" checked={selectedSourceVersions.includes(version.id)} onChange={(event) => toggleSource(version.id, event.target.checked)} style={{ marginTop: 3 }} />
                <span><strong style={{ fontSize: 13 }}>{resource.title}</strong><small style={{ display: "block", color: "#9aa5b5", marginTop: 4 }}>v{version.version_number} · {version.original_filename} · {version.extraction?.segment_count ?? 0} segments · {resource.visibility}</small></span>
              </label>
            )))}
            {!resources.some((resource) => resource.versions.some((version) => version.extraction?.status === "extracted")) && <p style={{ color: "#9aa5b5", fontSize: 13 }}>No successfully extracted sources are available yet. Upload materials in Coursework resources first.</p>}
            {!blueprints.length && <p style={{ color: "#ffb18b", fontSize: 13 }}>No approved blueprint is available. An examiner or moderator must approve a blueprint before generation.</p>}
            <button onClick={() => void generateQuestions()} disabled={busy || !blueprintVersionId || selectedSourceVersions.length === 0} style={{ ...action, width: "100%", marginTop: 16 }}>{busy ? "Generating…" : "Generate practice questions"}</button>
            <p style={{ color: "#8793a5", fontSize: 11, lineHeight: 1.5 }}>Generation is limited to 10 requests per hour and 30 questions per request. Generated questions remain private drafts until reviewed.</p>
          </section>

          <section style={panel}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
              <h2 style={{ fontSize: 17, margin: 0 }}>3. My question bank ({questions.length})</h2>
              <button onClick={() => void chooseSubject(subjectId)} disabled={busy} style={{ ...action, padding: "7px 10px", fontSize: 12, background: "#293242", color: "#f4f6fa" }}>Refresh</button>
            </div>
            {!questions.length && <p style={{ color: "#9aa5b5", fontSize: 13, marginTop: 16 }}>Your generated questions will appear here with their source references.</p>}
            {questions.map((question) => {
              const version = question.versions.find((item) => item.version_number === question.current_version_number) ?? question.versions[0];
              if (!version) return null;
              const options = version.response_schema.options;
              return <article key={question.id} style={{ border: "1px solid #364154", borderRadius: 10, padding: 14, marginTop: 12, background: "#0b1018" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                  <strong style={{ fontSize: 13 }}>{version.question_type.replaceAll("_", " ")}</strong>
                  <small style={{ color: "#55d5e8" }}>{version.marks} marks · {version.difficulty} · {version.status}</small>
                </div>
                <p style={{ lineHeight: 1.6 }}>{version.prompt}</p>
                {Array.isArray(options) && options.map((option) => {
                  if (!option || typeof option !== "object") return null;
                  const item = option as { id?: string; label?: string };
                  return <p key={item.id} style={{ color: "#cbd3df", fontSize: 13, margin: "6px 0" }}>{item.id}. {item.label}</p>;
                })}
                <div style={{ borderTop: "1px solid #293242", marginTop: 12, paddingTop: 10 }}>
                  <small style={{ color: "#55d5e8" }}>Source references</small>
                  {version.citations.map((citation) => <p key={citation.id} style={{ color: "#9aa5b5", fontSize: 11, lineHeight: 1.5 }}>{citation.source_locator}{citation.excerpt ? ` · ${citation.excerpt}` : ""}</p>)}
                </div>
              </article>;
            })}
          </section>
        </div>
      )}
      <footer style={{ color: "#778497", fontSize: 11, padding: "24px 0" }}>EXAMGEN AI · AI-generated questions are drafts, not predictions of a real examination. Formal approval remains a staff responsibility.</footer>
    </main>
  );
}
