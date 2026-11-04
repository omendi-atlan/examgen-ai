"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";

type Workspace = { id: string; name: string; slug: string };
type Subject = { id: string; name: string; description: string | null; resource_sharing_enabled: boolean };
type Segment = { id: string; locator: string; text: string };
type Version = {
  id: string;
  version_number: number;
  original_filename: string;
  extraction: { status: string; character_count: number; segment_count: number; error_message: string | null } | null;
};
type Resource = {
  id: string;
  title: string;
  subject_id: string | null;
  visibility: "private" | "cohort";
  current_version_number: number;
  versions: Version[];
};


type ScannedPage = { jpeg: Uint8Array; width: number; height: number };

async function buildScannedPdf(pages: ScannedPage[]): Promise<Blob> {
  if (pages.length === 0) throw new Error("Capture at least one page before creating a PDF.");
  const encoder = new TextEncoder();
  const objects: Uint8Array[] = [];
  const objectCount = 2 + pages.length * 3;
  const offsets: number[] = [0];
  let position = 0;
  const chunks: Uint8Array[] = [encoder.encode("%PDF-1.4\n%EXAMGEN-SCAN\n")];
  position += chunks[0].length;
  const addObject = (id: number, body: Uint8Array[]) => {
    offsets[id] = position;
    const prefix = encoder.encode(`${id} 0 obj\n`);
    const suffix = encoder.encode("\nendobj\n");
    chunks.push(prefix, ...body, suffix);
    position += prefix.length + body.reduce((sum, part) => sum + part.length, 0) + suffix.length;
  };
  const kids = pages.map((_, index) => `${3 + index * 3} 0 R`).join(" ");
  addObject(1, [encoder.encode("<< /Type /Catalog /Pages 2 0 R >>")]);
  addObject(2, [encoder.encode(`<< /Type /Pages /Kids [${kids}] /Count ${pages.length} >>`)]);
  pages.forEach((page, index) => {
    const pageId = 3 + index * 3;
    const contentId = pageId + 1;
    const imageId = pageId + 2;
    const width = 595.28;
    const height = Math.max(1, width * page.height / page.width);
    const content = encoder.encode(`q\n${width.toFixed(2)} 0 0 ${height.toFixed(2)} 0 0 cm\n/Im0 Do\nQ\n`);
    addObject(pageId, [encoder.encode(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${width.toFixed(2)} ${height.toFixed(2)}] /Resources << /XObject << /Im0 ${imageId} 0 R >> >> /Contents ${contentId} 0 R >>`,
    )]);
    addObject(contentId, [
      encoder.encode(`<< /Length ${content.length} >>\nstream\n`),
      content,
      encoder.encode("endstream"),
    ]);
    addObject(imageId, [
      encoder.encode(
        `<< /Type /XObject /Subtype /Image /Width ${page.width} /Height ${page.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${page.jpeg.length} >>\nstream\n`,
      ),
      page.jpeg,
      encoder.encode("\nendstream"),
    ]);
  });
  const xrefOffset = position;
  let xref = `xref\n0 ${objectCount + 1}\n0000000000 65535 f \n`;
  for (let id = 1; id <= objectCount; id += 1) {
    xref += `${String(offsets[id]).padStart(10, "0")} 00000 n \n`;
  }
  const trailer = encoder.encode(
    `${xref}trailer\n<< /Size ${objectCount + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`,
  );
  chunks.push(trailer);
  return new Blob(chunks, { type: "application/pdf" });
}
\nconst panel = { background: "#11151e", border: "1px solid #293242", borderRadius: 14, padding: 18 } as const;
const field = { width: "100%", padding: "11px 12px", marginTop: 6, borderRadius: 8, border: "1px solid #364154", background: "#0b1018", color: "#f4f6fa" } as const;
const action = { border: 0, borderRadius: 8, padding: "11px 15px", background: "#ff8a35", color: "#20140b", fontWeight: 800, cursor: "pointer" } as const;

export default function CourseworkResourcesPage() {
  const [apiBase, setApiBase] = useState(process.env.NEXT_PUBLIC_EXAMGEN_API_URL ?? "http://localhost:8000");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [subjects, setSubjects] = useState<Subject[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [subjectId, setSubjectId] = useState("");
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
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [scanPages, setScanPages] = useState<ScannedPage[]>([]);
  const videoRef = useRef<HTMLVideoElement>(null);
  const cameraStream = useRef<MediaStream | null>(null);

  useEffect(() => {
    if (!cameraOpen) return;
    let cancelled = false;
    async function startCamera() {
      try {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error("Camera scanning requires a supported browser and a secure HTTPS connection.");
        }
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        cameraStream.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        setCameraError("");
      } catch (cause) {
        setCameraError(cause instanceof Error ? cause.message : "Camera access was unavailable.");
      }
    }
    void startCamera();
    return () => {
      cancelled = true;
      cameraStream.current?.getTracks().forEach((track) => track.stop());
      cameraStream.current = null;
    };
  }, [cameraOpen]);

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
      if (available.length === 0) setNotice("You are signed in, but no active coursework workspace is assigned to this account.");
      else setNotice("Signed in. Choose your coursework workspace and subject.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed.");
    } finally { setBusy(false); }
  }

  async function chooseWorkspace(id: string) {
    setWorkspaceId(id); setSubjectId(""); setSubjects([]); setResources([]); setSelectedId(""); setSegments([]);
    if (!id) return;
    setBusy(true); setError("");
    try {
      const result = await api<Subject[]>(`/workspaces/${id}/subjects`);
      setSubjects(result);
      if (result.length === 0) setNotice("No subjects are currently assigned to this workspace.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load subjects."); }
    finally { setBusy(false); }
  }

  async function chooseSubject(id: string) {
    setSubjectId(id); setResources([]); setSelectedId(""); setSegments([]);
    if (!id) return;
    setBusy(true); setError("");
    try {
      const result = await api<Resource[]>(`/workspaces/${workspaceId}/subjects/${id}/resources`);
      setResources(result);
      setNotice(`Loaded ${result.length} resource(s) for this subject.`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load resources."); }
    finally { setBusy(false); }
  }

  async function refreshResources() {
    if (!workspaceId || !subjectId) return;
    setBusy(true); setError("");
    try {
      const result = await api<Resource[]>(`/workspaces/${workspaceId}/subjects/${subjectId}/resources`);
      setResources(result);
      setNotice("Processing status refreshed.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not refresh resources."); }
    finally { setBusy(false); }
  }


  async function captureScanPage() {
    const video = videoRef.current;
    if (!video || video.videoWidth === 0 || video.videoHeight === 0) {
      setCameraError("Wait for the camera preview before capturing a page.");
      return;
    }
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) {
      setCameraError("This browser could not prepare the scan image.");
      return;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((value) => value ? resolve(value) : reject(new Error("Could not encode the scan image.")), "image/jpeg", 0.9);
    });
    setScanPages((current) => [...current, {
      jpeg: new Uint8Array(await blob.arrayBuffer()),
      width: canvas.width,
      height: canvas.height,
    }]);
    setCameraError("");
  }

  function closeScanner() {
    setCameraOpen(false);
    cameraStream.current?.getTracks().forEach((track) => track.stop());
    cameraStream.current = null;
  }

  async function useScannedPages() {
    try {
      const pdf = await buildScannedPdf(scanPages);
      const scannedFile = new File([pdf], `coursework-scan-${new Date().toISOString().replace(/[:.]/g, "-")}.pdf`, {
        type: "application/pdf",
      });
      setFile(scannedFile);
      setScanPages([]);
      closeScanner();
      setNotice("Your scanned pages are ready as a PDF. Add a title and upload them to this subject.");
    } catch (cause) {
      setCameraError(cause instanceof Error ? cause.message : "Could not create the scanned PDF.");
    }
  }
\n  async function uploadResource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || !title.trim() || !workspaceId || !subjectId) {
      setError("Choose a workspace, subject, title and file."); return;
    }
    setBusy(true); setError(""); setNotice("");
    try {
      const body = new FormData();
      body.append("title", title.trim()); body.append("visibility", visibility); body.append("file", file);
      const created = await api<Resource>(
        `/workspaces/${workspaceId}/subjects/${subjectId}/resources`,
        { method: "POST", body },
      );
      setResources((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setSelectedId(created.id); setTitle(""); setFile(null);
      setNotice("Uploaded securely. Malware scanning and extraction/OCR are queued.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Upload failed."); }
    finally { setBusy(false); }
  }

  async function selectResource(resource: Resource) {
    setSelectedId(resource.id); setSegments([]); setError("");
    const version = resource.versions.at(-1);
    if (!version) return;
    try {
      const result = await api<Segment[]>(
        `/workspaces/${workspaceId}/subjects/${subjectId}/resources/${resource.id}/versions/${version.id}/segments`,
      );
      setSegments(result);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load extracted text."); }
  }


  async function downloadVersion(resource: Resource, version: Version) {
    setBusy(true); setError(""); setNotice("");
    try {
      const response = await fetch(
        `${base}/api/v1/workspaces/${workspaceId}/subjects/${subjectId}/resources/${resource.id}/versions/${version.id}/download`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) {
        const body = await response.json() as { detail?: string };
        throw new Error(body.detail ?? "Download could not be completed.");
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = version.original_filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
      setNotice("Your authorised source download has started.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Download failed.");
    } finally { setBusy(false); }
  }

  async function retryExtraction(resource: Resource, version: Version) {
    setBusy(true); setError(""); setNotice("");
    try {
      const updated = await api<Resource>(
        `/workspaces/${workspaceId}/subjects/${subjectId}/resources/${resource.id}/versions/${version.id}/retry`,
        { method: "POST" },
      );
      setResources((current) => current.map((item) => item.id === updated.id ? updated : item));
      setSegments([]);
      setNotice("Extraction has been safely requeued. Refresh to follow processing progress.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not retry extraction.");
    } finally { setBusy(false); }
  }

  async function appendVersion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const selected = resources.find((item) => item.id === selectedId);
    if (!selected || !versionFile) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const body = new FormData(); body.append("file", versionFile);
      const updated = await api<Resource>(
        `/workspaces/${workspaceId}/subjects/${subjectId}/resources/${selected.id}/versions`,
        { method: "POST", body },
      );
      setResources((current) => current.map((item) => item.id === updated.id ? updated : item));
      setVersionFile(null); setSegments([]);
      setNotice("New immutable version added. Its extraction is queued.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not append this version."); }
    finally { setBusy(false); }
  }

  const selected = resources.find((item) => item.id === selectedId) ?? null;
  const latest = selected?.versions.at(-1);
  const currentSubject = subjects.find((item) => item.id === subjectId);

  return (
    <main style={{ maxWidth: 1120, margin: "0 auto", padding: "28px 18px", color: "#f4f6fa" }}>
      <header style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", borderBottom: "1px solid #293242", paddingBottom: 16 }}>
        <div><Link href="/" style={{ color: "#ff8a35", textDecoration: "none", fontWeight: 900 }}>EXAMGEN AI</Link><p style={{ color: "#9aa5b5", fontSize: 11, letterSpacing: ".12em", margin: "5px 0 0" }}>STUDENT COURSEWORK · MY RESOURCES</p></div>
        <span style={{ color: "#55d5e8", fontSize: 12 }}>{token ? "STUDENT SESSION" : "SIGN IN REQUIRED"}</span>
      </header>

      <section style={{ margin: "25px 0" }}>
        <p style={{ color: "#ff8a35", fontSize: 11, fontWeight: 800, letterSpacing: ".15em" }}>LEARNING MATERIALS</p>
        <h1 style={{ fontSize: "clamp(28px,4vw,40px)", margin: "7px 0" }}>Coursework resources</h1>
        <p style={{ color: "#9aa5b5", lineHeight: 1.6, maxWidth: 760 }}>Upload lecture notes, slides, readings, worksheets, diagrams and previous assessments directly into a subject. Files are scanned and processed in the background; extracted text and OCR status remain attached to each source.</p>
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
            <button onClick={() => { setToken(""); setWorkspaces([]); setSubjects([]); setResources([]); setWorkspaceId(""); setSubjectId(""); setSelectedId(""); }} style={{ ...action, alignSelf: "end", background: "#293242", color: "#f4f6fa" }}>Sign out</button>
          </div>
        )}
        {error && <p role="alert" style={{ color: "#ff9a9a" }}>{error}</p>}
        {notice && <p role="status" style={{ color: "#75d9a5" }}>{notice}</p>}
      </section>

      {token && workspaceId && subjectId && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(260px,.85fr) minmax(0,1.4fr)", gap: 16 }}>
          <section style={panel}>
            <h2 style={{ fontSize: 17, marginTop: 0 }}>2. Add a resource</h2>
            <form onSubmit={uploadResource}>
              <label style={{ display: "block", fontSize: 13 }}>Resource title<input required maxLength={240} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Week 4 — Database normalisation" style={field} /></label>
              <label style={{ display: "block", fontSize: 13, marginTop: 12 }}>Visibility<select value={visibility} onChange={(event) => setVisibility(event.target.value as "private" | "cohort")} style={field}><option value="private">Private — only me</option>{currentSubject?.resource_sharing_enabled && <option value="cohort">Share with enrolled cohort</option>}</select></label>
              <label style={{ display: "block", fontSize: 13, marginTop: 12 }}>Upload a resource<input required type="file" accept=".pdf,.docx,.pptx,.txt,.md,application/pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} style={{ ...field, padding: 8 }} /></label>
              <button type="button" onClick={() => { setCameraError(""); setScanPages([]); setCameraOpen(true); }} style={{ ...action, width: "100%", marginTop: 10, background: "#263747", color: "#eaf7ff" }}> <span aria-hidden="true">▣</span> Scan pages with camera</button>
              {file && <p style={{ color: "#75d9a5", fontSize: 12 }}>Selected: {file.name}</p>}
              <p style={{ color: "#8793a5", fontSize: 11, lineHeight: 1.5 }}>Camera scanning requires HTTPS and browser permission. Captured pages are assembled into a PDF and processed through the same malware scan and OCR pipeline. Private is the default.</p>
              {cameraOpen && <div role="dialog" aria-label="Document scanner" aria-modal="true" style={{ border: "1px solid #364154", borderRadius: 10, padding: 12, marginTop: 12 }}>
                <h3 style={{ fontSize: 15, marginTop: 0 }}>Document scanner</h3>
                <video ref={videoRef} autoPlay muted playsInline style={{ width: "100%", maxHeight: 360, objectFit: "contain", background: "#05080d", borderRadius: 8 }} />
                {cameraError && <p role="alert" style={{ color: "#ff9a9a", fontSize: 12 }}>{cameraError}</p>}
                <p style={{ color: "#9aa5b5", fontSize: 12 }}>{scanPages.length} page(s) captured</p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  <button type="button" onClick={() => void captureScanPage()} style={action}>Capture page</button>
                  <button type="button" disabled={!scanPages.length} onClick={() => void useScannedPages()} style={action}>Create PDF ({scanPages.length})</button>
                  <button type="button" onClick={closeScanner} style={{ ...action, background: "#293242", color: "#f4f6fa" }}>Close scanner</button>
                </div>
                {scanPages.length > 0 && <button type="button" onClick={() => setScanPages((current) => current.slice(0, -1))} style={{ ...action, marginTop: 8, background: "#422a2a", color: "#ffe2e2" }}>Remove last page</button>}
              </div>}
              <button type="submit" disabled={busy || !file || !title.trim()} style={{ ...action, width: "100%" }}>{busy ? "Uploading…" : "Upload to this subject"}</button>
            </form>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center", marginTop: 24 }}><h3 style={{ fontSize: 15, margin: 0 }}>Resources ({resources.length})</h3><button onClick={() => void refreshResources()} disabled={busy} style={{ ...action, padding: "7px 10px", fontSize: 12 }}>Refresh</button></div>
            {resources.length === 0 && <p style={{ color: "#9aa5b5", fontSize: 13 }}>No resources have been uploaded to this subject yet.</p>}
            {resources.map((resource) => {
              const version = resource.versions.at(-1);
              const state = version?.extraction?.status ?? "pending";
              return <button key={resource.id} onClick={() => void selectResource(resource)} style={{ display: "block", width: "100%", textAlign: "left", padding: 12, marginTop: 8, borderRadius: 9, border: selectedId === resource.id ? "1px solid #ff8a35" : "1px solid #364154", background: "#0b1018", color: "#f4f6fa", cursor: "pointer" }}>
                <strong>{resource.title}</strong><small style={{ display: "block", color: "#9aa5b5", marginTop: 5 }}>v{resource.current_version_number} · {state.replaceAll("_", " ")} · {resource.visibility}</small>
              </button>;
            })}
          </section>

          <section style={panel}>
            <h2 style={{ fontSize: 17, marginTop: 0 }}>3. Processing and extracted content</h2>
            {!selected && <p style={{ color: "#9aa5b5" }}>Select one of your resources to inspect its processing status and extracted text.</p>}
            {selected && <>
              <h3 style={{ marginBottom: 5 }}>{selected.title}</h3>
              <p style={{ color: "#9aa5b5", fontSize: 12 }}>{latest?.original_filename} · Version {latest?.version_number} · <strong style={{ color: "#55d5e8" }}>{(latest?.extraction?.status ?? "pending").replaceAll("_", " ")}</strong></p>
              {latest?.extraction?.error_message && <p role="alert" style={{ color: "#ffb18b" }}>Processing issue: {latest.extraction.error_message}</p>}
              <p style={{ color: "#9aa5b5", fontSize: 12 }}>{latest?.extraction?.character_count ?? 0} characters · {latest?.extraction?.segment_count ?? 0} segments</p>
              {latest && <div style={{ display: "flex", flexWrap: "wrap", gap: 8, margin: "12px 0" }}>
                <button type="button" disabled={busy} onClick={() => void downloadVersion(selected, latest)} style={{ ...action, background: "#293242", color: "#f4f6fa" }}>Download original</button>
                {latest.extraction?.status === "failed" && <button type="button" disabled={busy} onClick={() => void retryExtraction(selected, latest)} style={action}>Retry extraction</button>}
              </div>}
              <form onSubmit={appendVersion} style={{ borderTop: "1px solid #293242", paddingTop: 14, marginTop: 15 }}>
                <label style={{ display: "block", fontSize: 13 }}>Append a revised version<input type="file" required accept=".pdf,.docx,.pptx,.txt,.md" onChange={(event) => setVersionFile(event.target.files?.[0] ?? null)} style={{ ...field, padding: 8 }} /></label>
                <button type="submit" disabled={busy || !versionFile} style={{ ...action, marginTop: 10 }}>Add new version</button>
              </form>
              <div style={{ borderTop: "1px solid #293242", marginTop: 18, paddingTop: 12 }}>
                <h3 style={{ fontSize: 15 }}>Extracted source text</h3>
                {segments.length === 0 && <p style={{ color: "#9aa5b5", fontSize: 13 }}>No extracted text is available yet. Refresh the resource after the worker completes; scanned PDFs may require OCR.</p>}
                {segments.map((segment) => <article key={segment.id} style={{ borderTop: "1px solid #293242", padding: "12px 0" }}><small style={{ color: "#55d5e8" }}>{segment.locator}</small><p style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{segment.text}</p></article>)}
              </div>
            </>}
          </section>
        </div>
      )}
      <footer style={{ color: "#778497", fontSize: 11, padding: "24px 0" }}>EXAMGEN AI · Academic sources are untrusted input. Extraction is not automatically academically approved.</footer>
    </main>
  );
}
