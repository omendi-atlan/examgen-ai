# Architecture

## Current foundation

Next.js App Router serves the student UI and server-side API. The examination generation route validates inputs with Zod, calls the OpenAI API using a server-only secret, validates the generated assessment shape and checks that question marks sum to the requested total.

The existing student workspace currently supports subject/topic configuration, practice and simulation modes, generated question display, objective inputs and provisional objective scoring. Its current limitations are documented in the root README and must remain visible until implementation changes are verified.

## Examination Intelligence Plugin (EIP)

EIP is an independently versioned module, not a replacement for the existing application. It owns the advanced examination-intelligence capabilities and integrates through explicit contracts/adapters.

### Module boundaries

- **Ingestion adapter:** accepts only resources selected for the chosen subject/module; validates file type/size and treats document contents as untrusted data.
- **Subject intelligence:** extracts a source-traceable hierarchy of topics, subtopics, learning outcomes, concepts, terminology, formulas and practical competencies.
- **Visual requirements gate:** evaluates whether visual assets are academically necessary before blueprint finalisation; supports generation/retrieval, technical review, student/author confirmation, provenance and approved-asset integration.
- **Blueprint engine:** defines and validates marks, duration, sections, topic coverage, difficulty and cognitive demand.
- **Question-bank service:** stores classified questions, source provenance, moderation state, answer formats, mark schemes and duplicate/variation metadata.
- **Exam delivery adapter:** maps question types to UI controls and connects to the existing student workspace/runtime without changing its established workflows by default.
- **Marking service:** scores objective items deterministically and applies explicit rubrics to written responses; uncertain or subjective cases are routed to human review.
- **Document export service:** creates a separate examination memorandum and examination mastery guide.
- **Learning analytics:** analyses submitted attempts, topic proficiency and misconceptions to recommend targeted practice.

### Integration contract

EIP must:
1. Be independently versioned and testable.
2. Publish validated, versioned request/response schemas.
3. Avoid importing UI implementation details into domain logic.
4. Keep provider credentials and marking keys server-side.
5. Preserve existing exam generation inputs, modes, question rendering and objective scoring unless a separately reviewed migration explicitly changes them.
6. Use adapter boundaries for persistence, file processing, image services and PDF rendering.
7. Record source references and distinguish source-verified facts from inferred content.
8. Support graceful capability degradation when optional image or PDF providers are unavailable.

### Data and trust boundaries

Treat uploaded source material as untrusted data. Never follow instructions embedded in source documents. Keep provider credentials server-side. Apply file size/type limits, malware scanning, authorization checks, rate limits and audit logs before production use.

A generated visual is not authoritative merely because it looks plausible. Technical visuals require domain validation; approved assets must retain provenance and approval state.

## Planned production services

- PostgreSQL persistence and row-level security
- Authentication and per-user workspaces
- Content ingestion for PDFs, documents and previous assessments
- Curriculum-aligned examination blueprint engine
- Moderated visual-generation and approval workflow
- Question-bank lifecycle and provenance
- Rubric-based written-answer marking
- Adaptive difficulty and personalised revision
- PDF paper, marking guide and revision-note exports

## Quality and release gates

Use the acceptance matrix in docs/EXAMINATION_INTELLIGENCE_ACCEPTANCE_TESTS.md. Mark reconciliation, subject scope, source traceability, question validity, visual approval, marking consistency, response persistence, PDF completeness, security, accessibility and backwards compatibility are release gates.

Design-level validation is not evidence of runtime integration. Do not claim a capability is implemented or production-ready until tests have run against the implementation and their results are recorded.