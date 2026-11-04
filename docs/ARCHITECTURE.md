# Architecture

## Status and source of truth

The approved target architecture and reusable prompt/skill catalogue are documented in [EXAMGEN AI Skill Plan](EXAMGEN_AI_SKILL_PLAN.md). This file summarises the architecture decision. The target modules are planned capabilities, not claims about the current release.

## Current foundation (release 0.3.0)

- Next.js student workspace with coursework resource and question-bank experiences.
- Authoritative FastAPI API with PostgreSQL, SQLAlchemy and Alembic.
- Student-owned, subject-associated academic resources with private-by-default access, malware scanning, extraction/OCR, provenance and durable processing.
- Versioned learning outcomes and examination blueprints with staff approval.
- Versioned question bank, source citations, private AI-generated drafts, staff-only answer-key access and blueprint-fit validation.
- Playwright browser acceptance for the student coursework journey and CI qualification for PostgreSQL migrations and backend integration.
- Persistent examination attempts, autosave/submission lifecycle, formal exam assembly, objective/subjective marking, visual approval and PDF delivery remain future milestones.

The TypeScript Worker is now health-only. Its former unauthenticated examination-generation route returns HTTP 410 and cannot be used as an alternate generation or answer-key path.

## Approved target architecture

EXAMGEN AI will use an integrated central intelligence engine with independently testable domain modules. The generated student examination website must be delivered as HTML, CSS and browser JavaScript. The existing Next.js workspace may remain as the authoring/admin shell during a staged migration; it must not be destructively rewritten before feature parity and migration tests.

Python is the authoritative backend. The recommended foundation is FastAPI, Pydantic, SQLAlchemy, Alembic and PostgreSQL, with durable background processing and object storage for long-running document, visual and PDF workflows. The TypeScript Worker is transitional and now health-only; provider integration and application logic live behind Python services. Avoid dual sources of truth.

The target domain modules are academic ingestion, subject intelligence, visual intelligence, examination blueprints, question bank, answer/rubric intelligence, moderation, examination publishing, attempt management, marking, analytics, personalised revision, PDF production and administration.

## Core architecture rules

1. Uploaded documents are untrusted data; never follow embedded instructions as system instructions.
2. Keep provider credentials, answer keys and unreleased rubrics server-side.
3. Persist source provenance and immutable versions of published exams, questions, visuals and rubrics.
4. Require visual validation and explicit approval before publication whenever a visual is essential.
5. Score objective items deterministically on the server; apply rubric-assisted marking and human review to subjective responses.
6. Enforce authentication, object-level authorisation, rate limits, upload limits, audit logs and retention controls.
7. Require tests and documented acceptance criteria for each phase.

See [Roadmap](ROADMAP.md) for migration phases and [EXAMGEN AI Skill Plan](EXAMGEN_AI_SKILL_PLAN.md) for the full data model, API, skill catalogue, moderation gates and definition of done.
