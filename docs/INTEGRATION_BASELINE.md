# EXAMGEN AI integration baseline

**Branch:** `integration/examgen-ai-release-2026-11`  
**Baseline:** PR #29 head `e7021acd8a60385f86e971a544269c52c8b8f70f`  
**Protected branch:** `main` — unchanged; no PRs merged.

## Why this baseline

The baseline is the latest clean, source-cited question-bank implementation stacked on the coursework browser qualification and blueprint foundation:

1. Coursework browser qualification: PR #26, `build/coursework-browser-qualification`.
2. Versioned blueprint foundation: PR #27, `build/blueprint-foundation-integration`.
3. Source-cited question bank: PR #29, `build/question-bank-generation-clean`.

PR #29 is selected as the integration baseline because its question-bank model and migration are the newer clean implementation, not because it already contains the practice-attempt or visual features.

## Reconciliation findings

PR #30 (visual intelligence) is based on PR #25's older question-bank/practice branch. The branches diverge from the shared coursework ancestry; they are not a safe fast-forward stack.

- PR #29 question-bank migration: `f7c2a91d4e60`, parent `c2e8a5f74190`.
- PR #30 older question-bank migration: `e7b4c2a91d60`.
- PR #30 practice migration: `f2c8a6d1b930`, parent `e7b4c2a91d60`.
- PR #30 visual migration: `a3f9d2c71b48`, parent `f2c8a6d1b930`.

The older PR #30 question-bank schema is not interchangeable with PR #29's schema. Directly retargeting or merging PR #30 would risk duplicate tables/models and an invalid Alembic lineage.

## Canonical integration sequence

The target Alembic lineage must be:

`d4a8c1f7b620` → `c2e8a5f74190` → `f7c2a91d4e60` → **new practice-attempt migration** → **new visual-intelligence migration**

Implementation rules:

- Port practice exam/attempt behaviour onto PR #29's canonical QuestionVersion model and field names.
- Do not carry forward the obsolete `e7b4c2a91d60` question-bank migration or duplicate `questions` / `question_versions` tables.
- Reconcile visual moderation queries against the canonical question-bank schema and approved-question status.
- Preserve immutable question versions, citations, server-authoritative deadlines, autosave, submission finalisation and answer-key non-disclosure.
- Keep every migration additive and verify both clean PostgreSQL upgrades and upgrades from the supported prior schema.

## Remaining work / release gates

- Integrate durable practice exams and attempts against the canonical question schema.
- Integrate visual requirement analysis, versioned assets and moderation against canonical blueprints/questions.
- Add the visual authoring/review UI and browser accessibility coverage.
- Run the complete coursework → blueprint → question bank → visual moderation → exam → attempt → marking workflow.
- Qualify actual AI provider, S3-compatible staging storage, ClamAV, ingress/TLS, backup/restore and worker recovery. Mocked CI is not live-provider evidence.
- Generate and verify the full ZIP from this integration branch only after qualification.

See [release-quality issue #31](https://github.com/omendi-atlan/examgen-ai/issues/31).

## Safety

All source PRs remain unmerged. Do not merge this branch or any PR into `main` without separate explicit approval.
