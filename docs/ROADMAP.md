# Roadmap

The approved target scope, module contracts and reusable prompt/skill catalogue are defined in [EXAMGEN AI Skill Plan](EXAMGEN_AI_SKILL_PLAN.md). This roadmap distinguishes current foundation from future implementation.

## Current foundation — release 0.2.0

The repository currently has a Next.js student workspace, TypeScript Cloudflare Worker generation endpoint, initial question schema/mark-total validation, Docker files and CI. Persistent student attempts, document ingestion, a reusable question bank, visual approval, comprehensive moderation, analytics and PDF exports are not yet implemented.

## Approved delivery phases

### Phase 0 — Architecture and migration foundation (implementation in progress)
- [x] Map existing UI and Worker behaviour.
- [x] Establish the Python API service boundary, typed settings, shared SQLAlchemy metadata and Alembic migration path.
- [x] Add FastAPI liveness/readiness endpoints, Python packaging, health-contract tests and a dedicated CI job.
- [x] Add the API and PostgreSQL services alongside the existing Next.js container.
- [x] Preserve current frontend and Worker behaviour; no domain logic has been duplicated or removed.
- [ ] Confirm repository CI and integrated container startup before closing this phase.

### Phase 1 — Persistent core and security (implementation in progress)
- [x] Add canonical user, workspace, membership and audit-event models with tenant relationships and uniqueness constraints.
- [x] Add the first reviewed Alembic migration for the identity and audit schema.
- [ ] Implement authentication and enforce role- and workspace-scoped authorisation on API resources.
- [ ] Verify migration and tenant-isolation behaviour against PostgreSQL integration tests.
- [ ] Add server-side examination and attempt models with immutable versions.

### Phase 2 — Academic ingestion and subject intelligence
- PDF/document ingestion, OCR path, source citations, taxonomy and classification review.

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

Every phase requires automated tests, documented acceptance criteria, security review appropriate to the change and human review of academic moderation policies. Do not mark a roadmap item complete until code, tests and operational documentation demonstrate it. Do not expose formal answer keys or unreleased rubrics to the browser.
