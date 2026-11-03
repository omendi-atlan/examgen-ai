# Roadmap

## Phase 1 — Reliable examination engine (in progress)

1. Harden generation input validation, output schema checks, timeout handling and provider error handling.
2. Keep formal simulation answer keys and explanations out of browser responses.
3. Remove bundled sample answer keys from the production frontend.
4. Implement server-side attempt creation, answer submission, objective marking and rubric-assisted written marking.
5. Persist attempts and results; prevent duplicate or altered submissions.
6. Add automated tests for validation, mark totals, mode-specific answer exposure and submission integrity.

## Subsequent phases

7. Content intelligence: PDF/document ingestion, source citations, topic extraction and examination blueprints.
8. Question bank: classification, provenance, quality review, duplicate detection and reuse.
9. Visual intelligence: identify visual requirements, generate diagrams, require approval and attach approved assets.
10. Learning intelligence: adaptive difficulty, error analysis, personalised revision plans and spaced retrieval.
11. Deliverables: examination PDFs, answer keys, examiner notes and student revision PDFs.
12. Production readiness: authentication, accessibility, security review, load tests, monitoring and backups.

Each phase requires tests, documented acceptance criteria and review before release. Student accounts remain deferred until the core examination workflow is reliable.
