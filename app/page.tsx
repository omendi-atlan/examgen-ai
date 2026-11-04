import Link from "next/link";

const tile = {
  border: "1px solid #293242",
  borderRadius: 16,
  padding: 22,
  background: "#11151e",
  display: "flex",
  flexDirection: "column" as const,
  gap: 12,
};

export default function Home() {
  return (
    <main style={{ maxWidth: 1120, margin: "0 auto", padding: "34px 20px", color: "#f4f6fa" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #293242", paddingBottom: 18 }}>
        <strong style={{ fontSize: 20, letterSpacing: ".04em" }}>EXAMGEN <span style={{ color: "#ff8a35" }}>AI</span></strong>
        <span style={{ color: "#55d5e8", fontSize: 11, letterSpacing: ".12em" }}>PERSONAL LEARNING WORKSPACE</span>
      </header>

      <section style={{ padding: "52px 0 30px", maxWidth: 780 }}>
        <p style={{ color: "#ff8a35", fontSize: 11, fontWeight: 800, letterSpacing: ".16em" }}>LEARN FROM YOUR OWN COURSEWORK</p>
        <h1 style={{ fontSize: "clamp(34px,5vw,54px)", lineHeight: 1.08, margin: "12px 0" }}>Your material. Your question bank. Your exam preparation.</h1>
        <p style={{ color: "#9aa5b5", lineHeight: 1.7, fontSize: 16 }}>Upload your subject resources first. EXAMGEN AI extracts and organises the material, then uses approved assessment blueprints to generate source-cited practice questions. Your private uploads stay private by default.</p>
      </section>

      <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(250px,1fr))", gap: 14 }}>
        <article style={tile}>
          <span style={{ color: "#ff8a35", fontSize: 11, fontWeight: 800 }}>01 · COURSEWORK</span>
          <h2 style={{ fontSize: 22, margin: 0 }}>Upload your study resources</h2>
          <p style={{ color: "#9aa5b5", lineHeight: 1.6, margin: 0 }}>Add lecture notes, slides, readings, worksheets, diagrams and previous assessments to the correct subject. Track scanning, extraction and revisions.</p>
          <Link href="/coursework" style={{ color: "#ff8a35", fontWeight: 800, textDecoration: "none", marginTop: "auto" }}>Open coursework resources →</Link>
        </article>

        <article style={tile}>
          <span style={{ color: "#55d5e8", fontSize: 11, fontWeight: 800 }}>02 · QUESTION BANK</span>
          <h2 style={{ fontSize: 22, margin: 0 }}>Generate source-cited questions</h2>
          <p style={{ color: "#9aa5b5", lineHeight: 1.6, margin: 0 }}>Select extracted resources and an approved blueprint. Generate private draft questions with topic, learning-outcome and source references.</p>
          <Link href="/question-bank" style={{ color: "#55d5e8", fontWeight: 800, textDecoration: "none", marginTop: "auto" }}>Open question bank →</Link>
        </article>

        <article style={{ ...tile, opacity: .78 }}>
          <span style={{ color: "#b5a0ff", fontSize: 11, fontWeight: 800 }}>03 · PRACTICE EXAMINATIONS</span>
          <h2 style={{ fontSize: 22, margin: 0 }}>Attempt timed simulations</h2>
          <p style={{ color: "#9aa5b5", lineHeight: 1.6, margin: 0 }}>The next delivery adds assembled examination papers, timed attempts, autosave, durable submissions and server-side marking.</p>
          <span style={{ color: "#b5a0ff", fontSize: 12, fontWeight: 800, marginTop: "auto" }}>IN IMPLEMENTATION · NOT YET RELEASED</span>
        </article>
      </section>

      <section style={{ borderTop: "1px solid #293242", marginTop: 30, paddingTop: 20 }}>
        <p style={{ color: "#8793a5", fontSize: 12, lineHeight: 1.6 }}>Academic extraction is not the same as academic approval. Generated questions remain private drafts until an authorised reviewer approves them. Answer keys and unreleased marking rubrics are never included in student question-bank responses.</p>
      </section>
    </main>
  );
}
