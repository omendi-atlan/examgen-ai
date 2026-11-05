# EIP Implementation Skill Plan

This document is the implementation playbook for the standalone Examination Intelligence Plugin. Follow the phases in order; do not skip acceptance gates.

## Working rules

- Work only on an isolated feature branch until review.
- Read the existing application contracts before changing code.
- Prefer additive adapters and feature flags over invasive edits to the student workspace.
- Preserve current API behaviour and practice/simulation semantics.
- Never mark an unimplemented capability as complete.
- Keep answer keys and provider secrets server-side.
- Treat student uploads as untrusted data and retain source provenance.
- Record test evidence for each phase.

## Phase A — Repository reconnaissance and baseline

1. Map the current frontend, generation API, deployment and CI workflows.
2. Record existing request/response schemas and representative fixtures.
3. Run baseline build, lint, typecheck and existing tests where available.
4. Capture current practice-mode, simulation-mode and objective-scoring behaviour.
5. Document compatibility risks before writing integration code.

**Exit:** baseline is reproducible and compatibility contracts are documented.

## Phase B — Standalone module skeleton

1. Create a separately versioned EIP package/module.
2. Define a capability manifest and configuration schema.
3. Define versioned domain types for source documents, subject models, blueprints, questions, visuals, attempts, marking results and exports.
4. Define adapter interfaces for AI, file extraction, storage, image services and PDF rendering.
5. Add unit-test scaffolding and feature flags.

**Exit:** EIP can be imported/tested independently and has no UI/provider coupling in its domain layer.

## Phase C — Subject intelligence and provenance

1. Add safe file validation and ingestion adapters for agreed formats.
2. Extract text and structural metadata.
3. Classify topics, subtopics, learning outcomes, definitions, formulas and practical skills.
4. Attach source IDs/page or section references to extracted claims.
5. Mark unsupported or uncertain content explicitly.

**Exit:** source traceability and prompt-injection tests pass.

## Phase D — Visual gate and blueprint

1. Evaluate subject/assessment requirements for visual necessity.
2. Create visual requirements before blueprint finalisation.
3. Generate/retrieve candidate assets through adapters.
4. Require technical validation and explicit approval.
5. Build blueprint constraints and reconcile marks, time, topics, difficulty and cognitive demand.

**Exit:** visual approval and blueprint validation tests pass.

## Phase E — Question bank and moderation

1. Generate questions from the approved blueprint and subject model.
2. Enforce question schema, source traceability and marking criteria.
3. Detect duplicates and unsafe reuse of previous-paper wording.
4. Add moderation states and reviewer feedback.
5. Reject ambiguous, out-of-scope or unmarkable items.

**Exit:** question-quality acceptance tests pass.

## Phase F — Exam runtime integration

1. Define an adapter from EIP question records to existing exam rendering.
2. Support text inputs, text areas, selectable options, dropdowns, matching, calculation and visual question controls.
3. Add attempt persistence, autosave, review flags and safe submission.
4. Preserve practice and simulation modes.
5. Prevent formal answer-key exposure and duplicate/tampered submissions.

**Exit:** runtime tests and all existing regression tests pass.

## Phase G — Marking and learning intelligence

1. Keep objective marking deterministic.
2. Apply explicit rubrics to written responses.
3. Escalate uncertain or subjective marking for human review.
4. Analyse topic-level evidence from persisted attempts.
5. Generate targeted practice recommendations without unsupported readiness guarantees.

**Exit:** marking and analytics acceptance tests pass.

## Phase H — PDF deliverables

1. Generate the examination memorandum.
2. Generate the separate examination mastery study guide.
3. Verify all questions, marks, answer references and explanations against the approved paper.
4. Validate diagrams, fonts, tables, pagination and legibility.

**Exit:** PDF completeness and consistency tests pass.

## Phase I — Qualification and release

1. Execute every P0 acceptance test and record evidence.
2. Execute P1 tests or document approved deferrals and mitigations.
3. Run security, privacy and accessibility reviews.
4. Run platform regression, build, lint, typecheck and deployment checks.
5. Verify feature-flag disablement and rollback.
6. Publish release notes and compatibility matrix.
7. Qualify EIP only after all mandatory gates pass.

## Required evidence artefacts

- Baseline report.
- Module/API contract documentation.
- Test fixture inventory.
- Acceptance test results.
- Security and accessibility review.
- PDF and visual quality samples.
- Integration/rollback notes.
- Release notes and version metadata.
