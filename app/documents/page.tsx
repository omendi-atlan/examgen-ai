"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type QualityReport = {
  outcome: string;
  character_count: number;
  segment_count: number;
  page_count: number | null;
  reasons: string[];
  automatically_approved: boolean;
};
type Segment = { id: string; ordinal: number; locator: string; text: string; metadata: Record<string, unknown> };
type ExtractionReview = {
  id: string;
  version_id: string;
  decision: "accepted" | "rejected";
  rationale: string;
  reviewed_by: string;
  created_at: string;
};
type Version = {
  id: string;
  version_number: number;
  original_filename: string;
  created_at: string;
  extraction: {
    status: string;
    parser_name: string;
    parser_version: string;
    page_count: number | null;
    character_count: number;
    segment_count: number;
    error_message: string | null;
    quality_report: QualityReport;
  } | null;
  classifications: Array<{ subject_name: string; topic_name: string; method: string }>;
};
type AcademicDocument = {
  id: string;
  title: string;
  current_version_number: number;
  updated_at: string;
  versions: Version[];
};

const inputStyle = { width: "100%", padding: "11px 12px", borderRadius: 9, border: "1px solid #303a49", background: "#0c1119", color: "white", marginTop: 7 } as const;
const buttonStyle = { border: 0, borderRadius: 9, background: "#ff8a35", color: "#20140b", padding: "11px 16px", fontWeight: 800, cursor: "pointer" } as const;

export default function DocumentReviewPage() {
  const [apiBase, setApiBase] = useState(process.env.NEXT_PUBLIC_EXAMGEN_API_URL ?? "http://localhost:8000");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [token, setToken] = useState("");
  const [documents, setDocuments] = useState<AcademicDocument[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [segments, setSegments] = useState<Segment[]>([]);
  const [reviews, setReviews] = useState<ExtractionReview[]>([]);
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const selectedDocument = documents.find((item) => item.id === documentId) ?? null;
  const selectedVersion = selectedDocument?.versions.find((item) => item.id === versionId) ?? null;
  const quality = selectedVersion?.extraction?.quality_report;
  const base = apiBase.replace(/\/$/, "");

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${base}/api/v1${path}`, {
      ...init,
      headers: {
        ...(init.headers ?? {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    const data: unknown = await response.json();
    if (!response.ok) {
      const detail = typeof data === "object" && data !== null && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : "The API request could not be completed.";
      throw new Error(detail);
    }
    return data as T;
  }

  async function signIn(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`${base}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json() as { access_token?: string; detail?: string };
      if (!response.ok || !data.access_token) throw new Error(data.detail ?? "Sign-in failed.");
      setToken(data.access_token);
      setNotice("Signed in. Enter your workspace ID and load its academic documents.");
      setPassword("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  async function loadDocuments(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await request<AcademicDocument[]>(`/workspaces/${workspaceId.trim()}/documents`);
      setDocuments(result);
      setDocumentId(result[0]?.id ?? "");
      setVersionId(result[0]?.versions.at(-1)?.id ?? "");
      setSegments([]);
      setReviews([]);
      setNotice(`Loaded ${result.length} document(s) from the selected workspace.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load documents.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!token || !workspaceId || !documentId || !versionId) {
      setSegments([]);
      setReviews([]);
      return;
    }
    let active = true;
    setBusy(true);
    async function loadSelectedVersion() {
      try {
        const [segmentResult, reviewResult] = await Promise.all([
          request<Segment[]>(`/workspaces/${workspaceId}/documents/${documentId}/versions/${versionId}/segments`),
          request<ExtractionReview[]>(`/workspaces/${workspaceId}/documents/${documentId}/versions/${versionId}/extraction-reviews`),
        ]);
        if (active) {
          setSegments(segmentResult);
          setReviews(reviewResult);
          setError("");
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Could not load source review data.");
      } finally {
        if (active) setBusy(false);
      }
    }
    void loadSelectedVersion();
    return () => { active = false; };
  }, [token, workspaceId, documentId, versionId, base]);

  async function submitReview(decision: "accepted" | "rejected") {
    if (!selectedDocument || !selectedVersion || rationale.trim().length < 3) {
      setError("Enter a meaningful rationale before submitting the review.");
      return;
    }
    setReviewBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await request<ExtractionReview>(
        `/workspaces/${workspaceId}/documents/${documentId}/versions/${versionId}/extraction-reviews`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision, rationale: rationale.trim() }),
        },
      );
      setReviews((current) => [...current, created]);
      setRationale("");
      setNotice(`Extraction review recorded: ${decision}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not record extraction review.");
    } finally {
      setReviewBusy(false);
    }
  }

  const statusLabel = useMemo(() => selectedVersion?.extraction?.status.replaceAll("_", " ") ?? "not processed", [selectedVersion]);
  const panelStyle = { background: "#11151e", border: "1px solid #262e3b", borderRadius: 15, padding: 20 } as const;
  const canAccept = selectedVersion?.extraction?.status === "extracted"
    && (selectedVersion.extraction.character_count > 0)
    && (selectedVersion.extraction.segment_count > 0);

  return (
    <main style={{ maxWidth: 1180, margin: "0 auto", padding: "28px 18px", color: "#f4f6fa" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, borderBottom: "1px solid #262e3b", paddingBottom: 18 }}>
        <div><Link href="/" style={{ color: "#ff8a35", textDecoration: "none", fontWeight: 900, letterSpacing: ".1em" }}>EXAMGEN AI</Link><div style={{ color: "#9aa5b5", fontSize: 12, marginTop: 5 }}>ACADEMIC SOURCE REVIEW</div></div>
        <span style={{ color: "#55d5e8", fontSize: 12 }}>{token ? "AUTHENTICATED SESSION" : "EXAMINER ACCESS"}</span>
      </header>

      <section style={{ margin: "26px 0" }}>
        <p style={{ color: "#ff8a35", letterSpacing: ".16em", fontSize: 10, fontWeight: 800 }}>INGESTION · EXTRACTION · PROVENANCE</p>
        <h1 style={{ fontSize: "clamp(28px, 4vw, 42px)", margin: "8px 0" }}>Document review workspace</h1>
        <p style={{ color: "#9aa5b5", maxWidth: 760, lineHeight: 1.65 }}>Inspect source versions, processing state, extraction-quality signals and source-addressable text before confirming academic classification.</p>
      </section>

      <section style={{ ...panelStyle, marginBottom: 16 }}>
        <h2 style={{ marginTop: 0, fontSize: 18 }}>1. Connect to your workspace</h2>
        <label style={{ display: "block", color: "#cbd3df", fontSize: 13 }}>Python API URL<input value={apiBase} onChange={(event) => setApiBase(event.target.value)} style={inputStyle} /></label>
        {!token ? (
          <form onSubmit={signIn} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 12, alignItems: "end" }}>
            <label style={{ color: "#cbd3df", fontSize: 13 }}>Email<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} style={inputStyle} /></label>
            <label style={{ color: "#cbd3df", fontSize: 13 }}>Password<input type="password" required value={password} onChange={(event) => setPassword(event.target.value)} style={inputStyle} /></label>
            <button type="submit" disabled={busy} style={buttonStyle}>{busy ? "Signing in…" : "Sign in"}</button>
          </form>
        ) : (
          <form onSubmit={loadDocuments} style={{ display: "grid", gridTemplateColumns: "minmax(220px,1fr) auto auto", gap: 12, alignItems: "end" }}>
            <label style={{ color: "#cbd3df", fontSize: 13 }}>Workspace ID<input required value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)} style={inputStyle} /></label>
            <button type="submit" disabled={busy || !workspaceId.trim()} style={buttonStyle}>Load documents</button>
            <button type="button" onClick={() => { setToken(""); setDocuments([]); setSegments([]); setReviews([]); setWorkspaceId(""); setDocumentId(""); setVersionId(""); }} style={{ ...buttonStyle, background: "#263141", color: "#e5eaf1" }}>Sign out</button>
          </form>
        )}
        {error && <p role="alert" style={{ color: "#ff9a9a" }}>{error}</p>}
        {notice && <p role="status" style={{ color: "#55d5e8" }}>{notice}</p>}
      </section>

      {token && documents.length > 0 && (
        <section style={{ display: "grid", gridTemplateColumns: "minmax(240px,.8fr) minmax(0,2fr)", gap: 16 }}>
          <aside style={panelStyle}>
            <h2 style={{ marginTop: 0, fontSize: 18 }}>2. Source documents</h2>
            {documents.map((document) => (
              <button key={document.id} onClick={() => { setDocumentId(document.id); setVersionId(document.versions.at(-1)?.id ?? ""); }} style={{ display: "block", width: "100%", textAlign: "left", border: document.id === documentId ? "1px solid #ff8a35" : "1px solid #303a49", borderRadius: 10, background: "#0c1119", color: "white", padding: 12, margin: "9px 0", cursor: "pointer" }}>
                <strong>{document.title}</strong><small style={{ display: "block", color: "#9aa5b5", marginTop: 5 }}>{document.versions.length} version(s) · current v{document.current_version_number}</small>
              </button>
            ))}
          </aside>

          <div style={{ display: "grid", gap: 16 }}>
            <section style={panelStyle}>
              <h2 style={{ marginTop: 0, fontSize: 18 }}>3. Extraction assessment</h2>
              {selectedVersion ? (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
                    <div><strong>{selectedDocument?.title}</strong><div style={{ color: "#9aa5b5", fontSize: 12 }}>{selectedVersion.original_filename} · Version {selectedVersion.version_number}</div></div>
                    <span style={{ border: "1px solid #514064", borderRadius: 99, padding: "6px 10px", color: "#d7caff", fontSize: 12, textTransform: "capitalize" }}>{statusLabel}</span>
                  </div>
                  <label style={{ display: "block", color: "#cbd3df", fontSize: 13, marginTop: 16 }}>Source version<select value={versionId} onChange={(event) => setVersionId(event.target.value)} style={inputStyle}>{selectedDocument?.versions.map((version) => <option key={version.id} value={version.id}>Version {version.version_number} — {version.original_filename}</option>)}</select></label>
                  {quality && <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(110px,1fr))", gap: 8, margin: "16px 0" }}>
                    {[[ "Characters", quality.character_count ], [ "Segments", quality.segment_count ], [ "Pages", quality.page_count ?? "—" ]].map(([label, value]) => <div key={String(label)} style={{ background: "#0c1119", borderRadius: 9, padding: 12 }}><small style={{ color: "#9aa5b5" }}>{label}</small><strong style={{ display: "block", fontSize: 20, marginTop: 4 }}>{value}</strong></div>)}
                  </div>}
                  {quality?.reasons.map((reason) => <p key={reason} style={{ color: "#ffbe86", fontSize: 13 }}>• {reason}</p>)}
                  <p style={{ color: "#9aa5b5", fontSize: 12 }}>Quality outcome: <strong style={{ color: "#55d5e8" }}>{quality?.outcome ?? "pending"}</strong>. Automated approval: no.</p>
                  {selectedVersion.classifications.length > 0 && <p style={{ color: "#9aa5b5", fontSize: 13 }}>Confirmed topics: {selectedVersion.classifications.map((item) => `${item.subject_name} / ${item.topic_name}`).join(", ")}</p>}
                  <div style={{ borderTop: "1px solid #303a49", marginTop: 18, paddingTop: 16 }}>
                    <h3 style={{ fontSize: 15, marginTop: 0 }}>5. Examiner decision</h3>
                    <p style={{ color: "#9aa5b5", fontSize: 12, lineHeight: 1.6 }}>Acceptance is available only for a completed, non-empty extraction. Rejection remains available for sources that require correction or reprocessing. Every decision requires a rationale and is permanently recorded.</p>
                    <label style={{ display: "block", color: "#cbd3df", fontSize: 13 }}>Review rationale<textarea required minLength={3} maxLength={4000} value={rationale} onChange={(event) => setRationale(event.target.value)} rows={3} style={{ ...inputStyle, resize: "vertical" }} placeholder="Explain the academic or extraction-quality reason for this decision." /></label>
                    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
                      <button type="button" disabled={reviewBusy || busy || !canAccept || rationale.trim().length < 3} onClick={() => void submitReview("accepted")} style={{ ...buttonStyle, opacity: !canAccept || rationale.trim().length < 3 ? 0.5 : 1 }}>Accept extraction</button>
                      <button type="button" disabled={reviewBusy || busy || !selectedVersion.extraction || rationale.trim().length < 3} onClick={() => void submitReview("rejected")} style={{ ...buttonStyle, background: "#63353b", color: "#fff" }}>Reject extraction</button>
                      {reviewBusy && <span style={{ color: "#9aa5b5", alignSelf: "center", fontSize: 12 }}>Saving decision…</span>}
                    </div>
                    <h4 style={{ fontSize: 13, marginBottom: 8 }}>Decision history ({reviews.length})</h4>
                    {reviews.length === 0 && <p style={{ color: "#9aa5b5", fontSize: 12 }}>No examiner decisions have been recorded for this version.</p>}
                    {reviews.map((review) => <article key={review.id} style={{ borderTop: "1px solid #262e3b", padding: "10px 0" }}>
                      <strong style={{ color: review.decision === "accepted" ? "#79d6a5" : "#ff9a9a", textTransform: "capitalize" }}>{review.decision}</strong>
                      <p style={{ margin: "5px 0", color: "#e2e7ef", fontSize: 13 }}>{review.rationale}</p>
                      <small style={{ color: "#788598" }}>{new Date(review.created_at).toLocaleString()} · Reviewer {review.reviewed_by}</small>
                    </article>)}
                  </div>
                </>
              ) : <p style={{ color: "#9aa5b5" }}>Choose a source version to review.</p>}
            </section>
            <section style={panelStyle}>
              <h2 style={{ marginTop: 0, fontSize: 18 }}>4. Extracted source text</h2>
              {busy && <p style={{ color: "#9aa5b5" }}>Loading source segments…</p>}
              {!busy && segments.length === 0 && <p style={{ color: "#9aa5b5" }}>No extracted segments are available yet. A queued or failed document may need processing or OCR.</p>}
              {segments.map((segment) => <article key={segment.id} style={{ borderTop: "1px solid #262e3b", padding: "13px 0" }}><small style={{ color: "#55d5e8" }}>{segment.locator}</small><p style={{ whiteSpace: "pre-wrap", lineHeight: 1.65, color: "#e2e7ef", marginBottom: 0 }}>{segment.text}</p></article>)}
            </section>
          </div>
        </section>
      )}
      <footer style={{ color: "#788598", fontSize: 11, padding: "26px 0" }}>EXAMGEN AI · Human review remains mandatory for source quality and subject/topic classification.</footer>
    </main>
  );
}
