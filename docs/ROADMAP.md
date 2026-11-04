# Roadmap

The approved target scope, module contracts and reusable prompt/skill catalogue are defined in [EXAMGEN AI Skill Plan](EXAMGEN_AI_SKILL_PLAN.md). This roadmap distinguishes current foundation from future implementation.

## Current foundation — release 0.3.0

The repository has a Next.js student workspace, transitional TypeScript Cloudflare Worker, authoritative Python API, PostgreSQL persistence, workspace identity and initial academic ingestion. Persistent examination attempts, reusable question-bank workflows, visual approval, comprehensive moderation, analytics and PDF exports remain future delivery.

## Approved delivery phases

### Phase 0 — Architecture and migration foundation
- [x] Map existing UI and Worker behaviour.
- [x] Establish the Python API service boundary, typed settings, shared SQLAlchemy metadata and Alembic migration path.
- [x] Add FastAPI liveness/readiness endpoints, Python packaging, health-contract tests and a dedicated CI job.
- [x] Add the API and PostgreSQL services alongside the existing Next.js container.
- [x] Preserve current frontend and Worker behaviour during the staged migration.

### Phase 1 — Persistent core and security (implementation in progress)
- [x] Add canonical user, workspace, membership and audit-event models.
- [x] Add the reviewed identity and audit migration.
- [x] Add registration, login, short-lived signed access tokens and workspace membership enforcement.
- [ ] Complete PostgreSQL integration, tenant-isolation, rate-limiting and security tests.
- [ ] Add server-side examination and attempt models with immutable versions.

### Phase 2 — Academic ingestion and subject intelligence (implementation in progress)
- [x] Secure workspace-scoped uploads for PDF, DOCX, PPTX, TXT and Markdown.
- [x] Enforce file-size limits, extension allowlists, file signatures, UTF-8 text validation and Office archive structure/expansion limits.
- [x] Store sources under generated private object keys; never use user filenames as filesystem paths.
- [x] Record immutable document versions, SHA-256 fingerprints, uploader, source reference/type, publisher and publication date.
- [x] Extract text with page, slide, paragraph and character-range locators.
- [x] Persist extraction status, parser identity/version, metadata and addressable text segments.
- [x] Establish explicit workspace-owned subject/topic taxonomy and human-confirmed version classification.
- [ ] Add OCR for image-only PDFs and scanned documents.
- [ ] Add malware scanning, managed object-storage adapter and asynchronous extraction workers.
- [ ] Add PostgreSQL integration tests, extraction review UI and source-citation acceptance tests.

### Phase 3 — Blueprint, question bank and answer intelligence
- Blueprint constraints, question lifecycle, provenance, deduplication, model answers and rubrics.

### Phase 4 — Visual intelligence and moderation
- Visual requirement analysis, generation adapter, validation, approval workflow and moderation report.
- Required visuals block publication until approval.

### Phase 5 — HTML/CSS/JavaScript examination delivery
- Versioned student examination packages, type-matched response controls, accessibility, timer and autosave.

### Phase 6 — Submission and marking
- Server-authoritative timing, durable submission, deterministic objective scoring and rubric-assisted subjective marking.

### Phase 7 — Analytics and personalised revision
- Topic/outcome performance, error analysis, adaptive practice and spaced revision.

### Phase 8 — PDF production
- Examination papers, memorandums, examiner guides and personalised student revision packs.

### Phase 9 — Production hardening
- Security, accessibility, load tests, monitoring, backups, disaster recovery and deployment operations.

## Release gates

Every phase requires automated tests, documented acceptance criteria, security review appropriate to the change and human review of academic moderation policies. Do not mark a roadmap item complete until code, tests and operational documentation demonstrate it. Uploaded academic files are untrusted input; extracted text must retain provenance and must never be treated as executable instructions. Do not expose formal answer keys or unreleased rubrics to the browser.
