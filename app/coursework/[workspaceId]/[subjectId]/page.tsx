"use client";

import { FormEvent, use, useCallback, useState } from "react";
import Link from "next/link";

type Segment = { id: string; locator: string; text: string };
type ResourceVersion = {
  id: string;
  version_number: number;
  original_filename: string;
  extraction: {
    status: string;
    character_count: number;
    segment_count: number;
    error_message: string | null;
  } | null;
};
type Resource = {
  id: string;
  title: string;
  subject_id: string | null;
  visibility: "private" | "cohort";
  current_version_number: number;
  versions: ResourceVersion[];
};

const panel = { background: "#11151e", border: "1px solid #293242", borderRadius: 14, padding: 18 } as const;
const field = { width: "100%", padding: "11px 12px", marginTop: 6, borderRadius: 8, border: "1px solid #364154", background: "#0b1018", color: "#f4f6fa" } as const;
const action = { border: 0, borderRadius: 8, padding: "11px 15px", background: "#ff8a35", color: "#20140b", fontWeight: 800, cursor: "pointer" } as const;

export default function CourseworkResourcesPage({
  params,
}: {
  params: Promise<{ workspaceId: string; subjectId: string }>;
}) {
  const { workspaceId, subjectId } = use(params);
  const [apiBase, setApiBase] = useState(process.env.NEXT_PUBLIC_EXAMGEN_API_URL ?? "http://localhost:8000");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [resources, setResources] = useState<Resource[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [segments, setSegments] = useState<Segment[]>([]);
  const [title, setTitle] = useState("");
  const [visibility, setVisibility] = useState<"private" | "cohort">("private");
  const [file, setFile] = useState<File | null>(null);
  const [versionFile, setVersionFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const base = apiBase.replace(/\/$/, "");
  const endpoint = `/api/v1/workspaces/${workspaceId}/subjects/${subjectId}/resources`;

  const request = useCallback(async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    const response = await fetch(`${base}/api/v1${path}`, {
      ...init,
      headers: { ...(init.headers ?? {}), Authorization: `Bearer ${token}` },
    });
    const data = await response.json() as T & { detail?: string };
    if (!response.ok) throw new Error(data.detail ?? "The request could not be completed.");
    return data;
  }, [base, token]);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(`${base}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json() as { access_token?: string; detail?: string };
      if (!response.ok || !data.access_token) throw new Error(data.detail ?? "Sign-in failed.");
      setToken(data.access_token);
      setPassword("");
      setNotice("Signed in. Load the resources attached to this subject.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed.");
    } finally { setBusy(false); }
  }

  const refresh = useCallback(async () => {
    if (!token) return;
    const result = await request<Resource[]>(endpoint);
    setResources(result);
    if (!selectedId && result.length) setSelectedId(result[0].id);
    if (selectedId && !result.some((item) => item.id === selectedId)) setSelectedId("");
  }, [endpoint, request, selectedId, token]);

  async function loadResources() {
    setBusy(true); setError("");
    try { await refresh(); setNotice("Coursework resources refreshed."); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load resources."); }
    finally { setBusy(false); }
  }

  async function uploadResource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || !title.trim()) { setError("Add a title and choose a resource file."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      const body = new FormData();
      body.append("title", title.trim());
      body.append("visibility", visibility);
      body.append("file", file);
      const created = await request<Resource>(endpoint, { method: "POST", body });
      setResources((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setSelectedId(created.id);
      setTitle(""); setFile(null);
      setNotice("Resource uploaded securely. Extraction/OCR is queued and will appear here when processing completes.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Upload failed.");
    } finally { setBusy(false); }
  }

  async function showSegments(resource: Resource) {
    setSelectedId(resource.id); setSegments([]); setError("");
    const version = resource.versions.at(-1);
    if (!version) return;
    try {
      const result = await request<Segment[]>(
        `${endpoint}/${resource.id}/versions/${version.id}/segments`,
      );
      setSegments(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load extracted text.");
    }
  }

  async function appendVersion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const selected = resources.find((item) => item.id === selectedId);
    if (!selected || !versionFile) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const body = new FormData();
      body.append("file", versionFile);
      const updated = await request<Resource>(`${endpoint}/${selected.id}/versions`, { method: "POST", body });
      setResources((current) => current.map((item) => item.id === updated.id ? updated : item));
      setVersionFile(null);
      setNotice("A new immutable version was added. Its extraction is queued.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not append this version.");
    } finally { setBusy(false); }
  }

  const selected = resources.find((item) => item.id === selectedId) ?? null;
  const latest = selected?.versions.at(-1);
  const status = latest?.extraction?.status ?? "pending";

  return (
    <main style={{ maxWidth: 1120, margin: "0 auto", padding: "28px 18px", color: "#f4f6fa" }}>
      <header style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", borderBottom: "1px solid #293242", paddingBottom: 16 }}>
        <div>
          <Link href="/" style={{ color: "#ff8a35", textDecoration: "none", fontWeight: 900 }}>EXAMGEN AI</Link>
          <p style={{ color: "#9aa5b5", fontSize: 11, letterSpacing: ".12em", margin: "5px 0 0" }}>SUBJECT COURSEWORK · MY RESOURCES</p>
        </div>
        <span style={{ color: "#55d5e8", fontSize: 12 }}>{token ? "STUDENT SESSION" : "SIGN IN REQUIRED"}</span>
      </header>

      <section style={{ margin: "25px 0" }}>
        <p style={{ color: "#ff8a35", fontSize: 11, fontWeight: 800, letterSpacing: ".15em" }}>LEARNING MATERIALS</p>
        <h1 style={{ fontSize: "clamp(28px,4vw,40px)", margin: "7px 0" }}>Coursework resources</h1>
        <p style={{ color: "#9aa5b5", lineHeight: 1.6, maxWidth: 760 }}>Upload lecture notes, slides, readings, worksheets, diagrams and previous assessments directly into this subject. Your files are scanned and processed in the background; extracted text and OCR status remain attached to the source.</p>
      </section>

      <section style={{ ...panel, marginBottom: 16 }}>
        <h2 style={{ fontSize: 17, marginTop: 0 }}>Your coursework session</h2>
        <label style={{ display: "block", fontSize: 13, color: "#cbd3df" }}>Python API URL
          <input value={apiBase} onChange={(event) => setApiBase(event.target.value)} style={field} />
        </label>
        {!token ? (
          <form onSubmit={signIn} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 12, alignItems: "end", marginTop: 12 }}>
            <label style={{ fontSize: 13 }}>Email<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} style={field} /></label>
            <label style={{ fontSize: 13 }}>Password<input type="password" required value={password} onChange={(event) => setPassword(event.target.value)} style={field} /></label>
            <button disabled={busy} style={action}>{busy ? "Signing in…" : "Sign in"}</button>
          </form>
        ) : (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
            <button onClick={() => void loadResources()} disabled={busy} style={action}>{busy ? "Loading…" : "Refresh resources"}</button>
            <button onClick={() => { setToken(""); setResources([]); setSegments([]); setSelectedId(""); }} style={{ ...action, background: "#293242", color: "#f4f6fa" }}>Sign out</button>
          </div>
        )}
        {error && <p role="alert" style={{ color: "#ff9a9a" }}>{error}</p>}
        {notice && <p role="status" style={{ color: "#75d9a5" }}>{notice}</p>}
      </section>

      {token && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(260px,.85fr) minmax(0,1.4fr)", gap: 16 }}>
          <section style={panel}>
            <h2 style={{ fontSize: 17, marginTop: 0 }}>Add a resource</h2>
            <form onSubmit={uploadResource}>
              <label style={{ display: "block", fontSize: 13 }}>Resource title
                <input required maxLength={240} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Week 4 — Database normalisation" style={field} />
              </label>
              <label style={{ display: "block", fontSize: 13, marginTop: 12 }}>Visibility
                <select value={visibility} onChange={(event) => setVisibility(event.target.value as "private" | "cohort")} style={field}>
                  <option value="private">Private — only me</option>
                  <option value="cohort">Cohort — only if staff enabled sharing</option>
                </select>
              </label>
              <label style={{ display: "block", fontSize: 13, marginTop: 12 }}>Upload or scan
                <input required type="file" accept=".pdf,.docx,.pptx,.txt,.md,application/pdf" capture="environment" onChange={(event) => setFile(event.target.files?.[0] ?? null)} style={{ ...field, padding: 8 }} />
              </label>
              <p style={{ color: "#8793a5", fontSize: 11, lineHeight: 1.5 }}>On supported mobile devices, Scan may open the camera. Image-only PDFs are sent through OCR when available. Files remain private by default.</p>
              <button type="submit" disabled={busy || !file || !title.trim()} style={{ ...action, width: "100%" }}>{busy ? "Uploading…" : "Upload to this subject"}</button>
            </form>
            <h3 style={{ fontSize: 15, marginTop: 25 }}>My subject resources ({resources.length})</h3>
            {resources.length === 0 && <p style={{ color: "#9aa5b5", fontSize: 13 }}>No resources loaded yet. Refresh to see your uploads.</p>}
            {resources.map((resource) => {
              const version = resource.versions.at(-1);
              const state = version?.extraction?.status ?? "pending";
              return <button key={resource.id} onClick={() => void showSegments(resource)} style={{ display: "block", width: "100%", textAlign: "left", padding: 12, marginTop: 8, borderRadius: 9, border: selectedId === resource.id ? "1px solid #ff8a35" : "1px solid #364154", background: "#0b1018", color: "#f4f6fa", cursor: "pointer" }}>
                <strong>{resource.title}</strong>
                <small style={{ display: "block", color: "#9aa5b5", marginTop: 5 }}>v{resource.current_version_number} · {state.replaceAll("_", " ")} · {resource.visibility}</small>
              </button>;
            })}
          </section>

          <section style={panel}>
            <h2 style={{ fontSize: 17, marginTop: 0 }}>Processing and extracted content</h2>
            {!selected && <p style={{ color: "#9aa5b5" }}>Select one of your resources to inspect its processing status and extracted text.</p>}
            {selected && (
              <>
                <h3 style={{ marginBottom: 5 }}>{selected.title}</h3>
                <p style={{ color: "#9aa5b5", fontSize: 12 }}>{latest?.original_filename} · Version {latest?.version_number} · <strong style={{ color: "#55d5e8" }}>{status.replaceAll("_", " ")}</strong></p>
                {latest?.extraction?.error_message && <p role="alert" style={{ color: "#ffb18b" }}>Processing issue: {latest.extraction.error_message}</p>}
                <p style={{ color: "#9aa5b5", fontSize: 12 }}>{latest?.extraction?.character_count ?? 0} characters · {latest?.extraction?.segment_count ?? 0} source segments</p>
                <form onSubmit={appendVersion} style={{ borderTop: "1px solid #293242", paddingTop: 14, marginTop: 15 }}>
                  <label style={{ display: "block", fontSize: 13 }}>Append a revised version
                    <input type="file" required accept=".pdf,.docx,.pptx,.txt,.md" onChange={(event) => setVersionFile(event.target.files?.[0] ?? null)} style={{ ...field, padding: 8 }} />
                  </label>
                  <button type="submit" disabled={busy || !versionFile} style={{ ...action, marginTop: 10 }}>Add new version</button>
                </form>
                <div style={{ borderTop: "1px solid #293242", marginTop: 18, paddingTop: 12 }}>
                  <h3 style={{ fontSize: 15 }}>Extracted source text</h3>
                  {segments.length === 0 && <p style={{ color: "#9aa5b5", fontSize: 13 }}>No extracted text is available yet. Refresh after the background worker completes; scanned PDFs may require OCR.</p>}
                  {segments.map((segment) => <article key={segment.id} style={{ borderTop: "1px solid #293242", padding: "12px 0" }}>
                    <small style={{ color: "#55d5e8" }}>{segment.locator}</small>
                    <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{segment.text}</p>
                  </article>)}
                </div>
              </>
            )}
          </section>
        </div>
      )}
      <footer style={{ color: "#778497", fontSize: 11, padding: "24px 0" }}>EXAMGEN AI · Uploaded academic content is processed as untrusted source material. Extraction is not automatically academically approved.</footer>
    </main>
  );
}
