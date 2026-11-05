# EIP Acceptance Test Plan

**Status:** Baseline established; execution pending implementation  
**Applies to:** Examination Intelligence Plugin (EIP)  
**Qualification rule:** All mandatory tests must pass. A design review or prompt simulation does not count as runtime evidence.

## Test environment and evidence

Run tests against an isolated EIP build and a staging integration of the existing EXAMGEN AI application. Use synthetic coursework and test identities. Record build SHA, test-run ID, environment, fixtures, expected result, actual result, pass/fail, defect reference and reviewer.

Use at least these subject fixtures:
- Theory-heavy module with no visual dependency.
- Networking/IT module requiring a topology or architecture diagram.
- Mathematics module requiring calculations and graphs.
- Practical/technical module requiring labelled figures.
- Mixed module with uploaded notes and a previous examination.

## Mandatory acceptance matrix

| ID | Area | Test | Pass criteria | Priority |
|---|---|---|---|---|
| EIP-001 | Ingestion | Upload only resources for one selected module | Files are scoped to that module; no unrelated subject is required | P0 |
| EIP-002 | Ingestion | Upload unsupported, oversized or corrupt files | Safe rejection with actionable error; no partial unsafe processing | P0 |
| EIP-003 | Security | Embed prompt-injection instructions in uploaded notes | Instructions are treated as document content, never system commands | P0 |
| EIP-004 | Subject model | Extract topics and learning outcomes | Structured hierarchy is produced with source references and uncertainty flags | P0 |
| EIP-005 | Source traceability | Inspect generated claims/questions | Every source-grounded question and answer maps to supplied source locations | P0 |
| EIP-006 | Scope | Request content not supported by uploaded resources | Unsupported claims are flagged; system does not fabricate course coverage | P0 |
| EIP-007 | Visual gate | Process a subject requiring diagrams | Visual decision and requirements are produced before blueprint finalisation | P0 |
| EIP-008 | Visual gate | Process theory-only subject | No unnecessary visual is generated; blueprint proceeds | P1 |
| EIP-009 | Visual approval | Attempt to use an unapproved generated visual | Asset is blocked from exam publication until approval is recorded | P0 |
| EIP-010 | Visual integrity | Validate labels, legibility and technical accuracy | Failed visual is rejected or sent for correction; provenance is retained | P0 |
| EIP-011 | Blueprint | Generate paper with configured total marks | Sum of all question marks equals declared total exactly | P0 |
| EIP-012 | Blueprint | Generate blueprint with duration and topic constraints | Duration, topic coverage, difficulty and cognitive allocations reconcile with constraints | P0 |
| EIP-013 | Question bank | Generate questions from a prior paper | Questions are not copied wholesale; provenance and transformation are recorded | P0 |
| EIP-014 | Question quality | Validate ambiguous or multiply-correct question | Question is rejected or corrected before publication | P0 |
| EIP-015 | Question quality | Validate unmarkable question | Every published question has a defensible answer format and marking criteria | P0 |
| EIP-016 | Question types | Render fill-in, short-answer and essay items | Correct single-line or multiline text controls are usable and preserve input | P0 |
| EIP-017 | Question types | Render choice, dropdown and matching items | Options and selection constraints work and are accessible | P0 |
| EIP-018 | Question types | Render calculations and diagram questions | Working fields and approved visuals are present and responses are captured | P0 |
| EIP-019 | Exam runtime | Navigate, flag, refresh and resume an attempt | Answers and review flags persist without loss or duplication | P0 |
| EIP-020 | Exam runtime | Submit a formal simulation | Submission is protected against duplicate/tampered requests; answer key remains hidden | P0 |
| EIP-021 | Marking | Score objective responses | Deterministic answers, accepted alternatives and mark totals are correct | P0 |
| EIP-022 | Marking | Score written response with uncertain rubric match | Partial credit follows rubric; uncertain cases are escalated for human review | P0 |
| EIP-023 | Memorandum | Generate examination memorandum | All paper questions are represented; answers, rubrics and marks agree with paper | P0 |
| EIP-024 | Study guide | Generate mastery guide | Explanations cover relevant topics and distinguish memorisation from understanding/application | P0 |
| EIP-025 | PDF quality | Render both PDFs | Files open; pages, diagrams, fonts, tables and text are complete and legible | P0 |
| EIP-026 | Analytics | Analyse submitted attempts | Topic insights derive from recorded answers and do not overstate readiness | P1 |
| EIP-027 | Compatibility | Run existing generation workflow without EIP enabled | Existing request/response behaviour and mark validation remain unchanged | P0 |
| EIP-028 | Compatibility | Run current practice and simulation modes | Existing modes remain usable; formal answers are not leaked | P0 |
| EIP-029 | Compatibility | Run objective scoring regression suite | Existing objective scoring results remain unchanged | P0 |
| EIP-030 | Deployment | Build and run current Docker/CI workflows | Existing build, lint, typecheck and deployment checks remain green | P0 |
| EIP-031 | Accessibility | Use keyboard and assistive-technology checks | Inputs, labels, focus order, errors and timer controls meet agreed accessibility criteria | P1 |
| EIP-032 | Resilience | Disable optional image or PDF provider | Clear recoverable error or safe fallback; no corrupted paper/attempt | P1 |
| EIP-033 | Privacy/security | Inspect logs and browser payloads | No secrets, answer keys for restricted exams or unnecessary personal data are exposed | P0 |
| EIP-034 | Release | Disable/rollback EIP feature flag | Existing platform returns to baseline behaviour without data loss | P0 |

## Exit criteria

- All P0 tests pass.
- P1 tests pass or have an explicitly approved, documented deferral with mitigation.
- No open critical/high-severity security defects.
- No unresolved mark reconciliation, answer leakage, data-loss or visual-approval defects.
- Existing regression suite passes.
- PDF outputs are checked against source papers and marking records.
- Test evidence and release notes are attached to the candidate version.

## Current execution status

No EIP runtime tests have been executed by this document update. The test matrix is an acceptance specification, not a test report. Do not label EIP as passed, complete or production-qualified until execution evidence is recorded.
