# Roadmap

The approved target scope, module contracts and reusable prompt/skill catalogue are defined in [EXAMGEN AI Skill Plan](EXAMGEN_AI_SKILL_PLAN.md). This roadmap distinguishes current foundation from future implementation.

## Current foundation — release 0.3.0

The repository has a Next.js student workspace, transitional TypeScript Cloudflare Worker, authoritative Python API, PostgreSQL persistence, workspace identity and academic ingestion. Persistent examination attempts, reusable question-bank workflows, visual approval, comprehensive moderation, analytics and PDF exports remain future delivery.

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
- [x] Add shared PostgreSQL-backed login and registration rate limiting with 429/Retry-After responses and concurrent atomicity tests.
- [x] Add role-based ingestion authorization, cross-workspace taxonomy isolation and fail-closed production configuration tests.
- [x] Add PostgreSQL-backed cross-tenant document access, taxonomy isolation and role-authorization integration tests.
- [x] Complete the route-by-route academic authorization and tenant-isolation matrix for upload, version, document, segment, taxonomy, classification and extraction-review endpoints.
- [ ] Complete production ingress/edge rate-limit verification.
- [ ] Complete representative document-load and OCR-heavy corpus throughput qualification.
- [ ] Add server-side examination and attempt models with immutable versions.

### Phase 2 — Academic ingestion and subject intelligence (implementation in progress)
- [x] Secure workspace-scoped uploads for PDF, DOCX, PPTX, TXT and Markdown.
- [x] Enforce file-size limits, extension allowlists, file signatures, UTF-8 text validation and Office archive structure/expansion limits.
- [x] Store sources under generated private object keys; never use user filenames as filesystem paths.
- [x] Record immutable document versions, SHA-256 fingerprints, uploader, source reference/type, publisher and publication date.
- [x] Extract text with page, slide, paragraph and character-range locators.
- [x] Persist extraction status, parser identity/version, metadata and addressable text segments.
- [x] Establish explicit workspace-owned subject/topic taxonomy and human-confirmed version classification.
- [x] Add page-level OCR fallback for image-only PDF pages using PDFium and Tesseract, retaining page locators and OCR provenance.
- [x] Add fail-closed ClamAV scanning before permanent upload acceptance; production startup requires scanning to be enabled.
- [x] Add a managed S3-compatible object-storage adapter, immutable-key migration utility, checksum verification, rollback guidance and private-bucket operational controls.
- [x] Add a durable database-backed extraction queue and separately deployed worker process.
- [x] Add PostgreSQL 16 CI migrations and multi-worker claim/lease-recovery integration tests.
- [x] Add an examiner review UI for source versions, extraction quality and source-addressable segments.
- [x] Connect the examiner UI to append-only accept/reject decisions, rationale capture and review history.
- [x] Persist extraction quality signals; extraction is never automatically approved.
- [x] Enforce PDF page, OCR pixel/time, presentation slide, Office archive expansion/ratio and extracted-character limits.
- [x] Add expiring worker leases, attempt accounting, expired-job recovery and fencing tokens to prevent stale workers committing results.
- [x] Add source-addressable segment locator and immutable-version provenance acceptance coverage.
- [x] Add concurrent extraction stress coverage for four 256 KB academic text sources and explicit PowerPoint slide/shape citation locators.
- [ ] Complete realistic multi-megabyte PDF and OCR-heavy scan throughput tests with multiple worker replicas.

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

See [Ingestion Security and Qualification Controls](INGESTION_SECURITY_QUALIFICATION.md) for release gates and deployment caveats.
