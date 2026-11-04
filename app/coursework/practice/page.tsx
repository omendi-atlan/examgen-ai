import Link from "next/link";

export default function PracticeExamsLandingPage() {
  return (
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "48px 20px", color: "#f4f6fa" }}>
      <p style={{ color: "#ff8a35", fontSize: 11, fontWeight: 800, letterSpacing: ".15em" }}>EXAMGEN AI · STUDENT COURSEWORK</p>
      <h1>Practice examination runner</h1>
      <p style={{ color: "#9aa5b5", lineHeight: 1.7 }}>The timed examination runner is delivered as a standalone semantic HTML, CSS and vanilla JavaScript package. It keeps the student exam experience independent of the authoring application shell.</p>
      <p><Link href="/practice/index.html" style={{ color: "#55d5e8", fontWeight: 800 }}>Open practice examination runner →</Link></p>
      <p><Link href="/coursework/questions" style={{ color: "#9aa5b5" }}>Return to your question bank</Link></p>
    </main>
  );
}
