# Roadmap

## Phase 1 — Reliable examination engine (in progress)

1. Harden generation input validation, output schema checks, timeout handling and provider error handling.
2. Keep formal simulation answer keys and explanations out of browser responses.
3. Remove bundled sample answer keys from the production frontend.
4. Implement server-side attempt creation, answer submission, objective marking and rubric-assisted written marking.
5. Persist attempts and results; prevent duplicate or altered submissions.
6. Add automated tests for validation, mark totals, mode-specific answer exposure and submission integrity.

## Phase 2 — Examination Intelligence Plugin (EIP): independent module foundation

EIP is a standalone, versioned module with explicit contracts and adapters. It must not replace the existing student workspace, generation endpoint, practice/simulation modes, objective scoring, deployment configuration or CI workflow.

1. Establish the plugin boundary, capability manifest, configuration contract and versioned input/output schemas.
2. Add subject-resource ingestion and classification adapters for supported file types; treat all uploaded material as untrusted data.
3. Build a source-traceable subject knowledge model with topics, subtopics, learning outcomes, terminology, formulas and practical competencies.
4. Implement the visual-requirements gate before the first examination blueprint is finalised; visual assets require technical validation and explicit approval before exam integration.
5. Implement blueprint construction and validation for marks, duration, topic coverage, question distribution, difficulty and cognitive demand.
6. Implement a reusable question-bank lifecycle with provenance, duplicate detection, moderation status and controlled reuse/variation.
7. Define the interactive exam runtime contract for supported answer controls, autosave, navigation, review flags, submission and attempt persistence.
8. Implement objective marking and rubric-assisted marking with uncertainty escalation and human review for subjective responses.
9. Generate two independent PDF deliverables: examination memorandum and examination mastery study guide.
10. Add topic-level performance analysis, misconception detection and adaptive practice recommendations.
11. Qualify the plugin against the acceptance suite in docs/EXAMINATION_INTELLIGENCE_ACCEPTANCE_TESTS.md before enabling production integration.

## Subsequent phases

12. Production persistence: PostgreSQL, authentication, per-user workspaces and row-level security.
13. Production security: file size/type limits, malware scanning, authorization, rate limits, audit logs and secret management.
14. Accessibility, responsive behaviour, load tests, monitoring, backup and recovery.
15. Controlled rollout, compatibility verification and release documentation.

## Release governance

- Student accounts remain deferred until the core examination workflow is reliable.
- EIP is independently versioned and must expose stable, documented contracts.
- Existing platform behaviour is a regression baseline; no EIP release may silently change it.
- Acceptance tests must be automated where practical and otherwise have recorded evidence.
- A design/specification pass is not a runtime test pass.
- A release is not production-qualified until all mandatory acceptance tests pass, security and accessibility reviews are complete, and integration compatibility is verified.
