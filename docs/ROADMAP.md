# Roadmap

The approved target scope, module contracts and reusable prompt/skill catalogue are defined in [EXAMGEN AI Skill Plan](EXAMGEN_AI_SKILL_PLAN.md). This roadmap distinguishes current foundation from future implementation.

## Current foundation — release 0.2.0

The repository currently has a Next.js student workspace, TypeScript Cloudflare Worker generation endpoint, initial question schema/mark-total validation, Docker files and CI. Persistent student attempts, document ingestion, a reusable question bank, visual approval, comprehensive moderation, analytics and PDF exports are not yet implemented.

## Approved delivery phases

### Phase 0 — Architecture and migration foundation
- Map existing UI and Worker behaviour.
- Define Python API contracts, domain schemas, database model and migration decisions.
- Add Python CI and a runnable FastAPI skeleton.
- Preserve current functionality.

### Phase 1 — Persistent core and security
- Authentication, roles, PostgreSQL, migrations, workspace isolation and audit events.
- Server-side examination and attempt models with immutable versions.

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
