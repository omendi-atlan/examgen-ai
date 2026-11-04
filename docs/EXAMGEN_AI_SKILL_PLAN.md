# EXAMGEN AI — Integrated Platform Skill & Architecture Plan

**Status:** Approved architecture baseline  
**Repository:** `omendi-atlan/examgen-ai`  
**Baseline release inspected:** `0.2.0`  
**Architecture decision:** Integrated central intelligence engine with specialised modules  
**Frontend requirement:** Generated examination websites use HTML, CSS and JavaScript  
**Backend requirement:** Python is the authoritative application and assessment backend

## 1. Purpose and scope

EXAMGEN AI is an academic examination intelligence platform. It must ingest and understand academic resources, classify subject knowledge, design and moderate examination blueprints, assemble reusable and newly generated questions, manage approved visuals, publish interactive examination websites, persist student attempts, mark responses, analyse performance and produce high-quality PDF learning deliverables.

The system is not considered complete merely because it can generate a list of questions. A complete examination lifecycle—from source material to moderated assessment, submission, marking and targeted revision—is the product objective.

This document establishes the approved architecture and reusable prompt/skill requirements. It does not assert that planned modules are already implemented.

## 2. Architecture principles

1. **One central source of truth:** subject records, source provenance, questions, visuals, blueprints, marking schemes, attempts and results share stable identifiers and version history.
2. **Academic validity before presentation:** examinations cannot be published until required moderation checks pass or an authorised moderator records an explicit, audited override.
3. **Visual-first when required:** determine visual requirements before final blueprint approval. Generate or retrieve required visuals, validate them and obtain approval before dependent questions are finalised.
4. **HTML/CSS/JavaScript examination delivery:** each student-facing examination is a responsive web experience using semantic HTML, CSS and browser JavaScript. Question types determine the correct response controls.
5. **Python is authoritative for backend operations:** scoring, submission validation, timing enforcement, answer-key access, persistence, analytics and PDF production must not rely on browser-side trust.
6. **Secure by default:** uploaded content is untrusted data; secrets remain server-side; access is authorised; student data is private; formal answer keys are never sent to the browser before release.
7. **Traceability:** generated claims, questions and answers should cite source documents/pages or be labelled as generated knowledge requiring verification.
8. **Human accountability:** subjective marking, high-impact moderation decisions and ambiguous academic content support human review.
9. **Testable modularity:** modules have explicit contracts, schemas, acceptance criteria and automated tests.
10. **Preserve working foundations:** evolve the current application incrementally; avoid unnecessary rewrites and maintain a documented migration path.

## 3. Target technical architecture

### 3.1 Frontend and examination delivery

- The existing Next.js workspace may remain as the administrative and authoring shell during migration.
- The generated student examination itself must be deliverable as HTML5, CSS3 and vanilla JavaScript assets (or equivalent framework-free browser output), responsive and accessible.
- Examination packages should contain a manifest, HTML entry point, styles, scripts and approved media references. They communicate with the backend API; they do not contain answer keys, private prompts or provider credentials.
- The authoring workspace can progressively adopt the same HTML/CSS/JS component and design conventions. Do not rewrite the existing Next.js workspace until parity, deployment and migration tests are demonstrated.
- Support keyboard navigation, clear focus states, semantic labels, accessible validation messages and mobile layouts.

### 3.2 Python backend

Recommended foundation:

- Python 3.12 or later, pinned and tested.
- FastAPI for versioned REST APIs and OpenAPI contracts.
- Pydantic for request, response and domain validation.
- SQLAlchemy 2.x and Alembic for persistence and migrations.
- PostgreSQL as the production relational database.
- Redis and Celery (or a compatible durable task queue) for long-running ingestion, generation, OCR, image processing and PDF tasks.
- Object storage abstraction for source files, approved visuals and generated exports.
- Pytest for unit, integration and contract tests.
- Structured logging, metrics, audit events, health checks and error monitoring.

The Python API is the authoritative backend. The existing TypeScript Cloudflare Worker is a transitional generation service only. Do not create two competing sources of truth. Migrate its useful provider integration behind Python service interfaces, verify parity, then retire or clearly decommission the Worker route. Keep API keys and provider secrets in server-side secret storage.

### 3.3 Core logical layers

1. Presentation and generated examination packages.
2. API gateway, authentication and authorisation.
3. Application orchestration and workflow state machine.
4. Academic intelligence and assessment domain services.
5. AI/provider adapters and deterministic validators.
6. Persistence, search/indexing, object storage and task queue.
7. Observability, audit and security controls.

## 4. Functional modules

| ID | Module | Required responsibility |
|---|---|---|
| M01 | Academic Ingestion | Upload/import PDF, DOCX, PPTX, XLSX, text and image resources; extract text, tables and page structure; OCR when needed; retain source identity and version. |
| M02 | Subject Intelligence | Build subject → module → topic → subtopic → learning outcome taxonomy; classify and tag source passages; identify gaps and duplicates. |
| M03 | Visual Intelligence | Detect visual requirements; retrieve source visuals or generate new diagrams; validate labels and semantics; version, approve and attach assets. |
| M04 | Examination Blueprint | Configure outcomes, topic weights, total marks, duration, question count/types, cognitive levels, difficulty and constraints. |
| M05 | Question Bank | Store reusable questions with source provenance, type, outcomes, marks, difficulty, status, versions, usage history and duplicate detection. |
| M06 | Answer Intelligence | Produce defensible model answers, worked solutions, explanations, accepted alternatives and marking rubrics. |
| M07 | Moderation and QA | Check accuracy, alignment, fairness, ambiguity, coverage, marks, timing, difficulty, answer validity, visual consistency and policy compliance. |
| M08 | Examination Publisher | Assemble versioned HTML/CSS/JS student examination websites from approved assessment packages. |
| M09 | Attempt Management | Create, resume, autosave, time, submit, lock and retain practice and formal attempts with audit events. |
| M10 | Marking Engine | Deterministically score objective items; apply transparent numeric tolerances; support rubric-guided subjective marking and human moderation. |
| M11 | Performance Analytics | Report outcomes, topic mastery, item statistics, distractor patterns, time use, attempts and progress with privacy controls. |
| M12 | Revision Intelligence | Generate targeted practice, spaced retrieval, active recall and revision schedules based on verified performance gaps. |
| M13 | PDF Production | Produce examination papers, memorandums, examiner notes and personalised study/revision guides with accessible, professional layouts. |
| M14 | Administration and Governance | Manage identities, roles, permissions, resource sharing, retention, audit, configuration, moderation overrides and release policies. |

## 5. Reusable prompt and skill catalogue

Each skill must have a versioned instruction, input schema, output schema, validation rules, failure behaviour, safety constraints and test fixtures. Skills should be orchestrated by the central workflow rather than operating as disconnected chat prompts.

### Academic understanding skills
- **S01 — Document Ingestion Skill:** extract content faithfully; preserve page/slide/sheet references; report unreadable or missing content; never invent extracted text.
- **S02 — Subject Classification Skill:** classify source passages against the explicit subject taxonomy and learning outcomes; provide confidence and evidence.
- **S03 — Knowledge Synthesis Skill:** produce topic summaries and concept relationships with citations to source material; distinguish source facts from external/general knowledge.

### Assessment design skills
- **S04 — Blueprint Design Skill:** translate learning outcomes and moderation constraints into a mark-balanced blueprint.
- **S05 — Question Generation Skill:** generate unambiguous, level-appropriate questions with outcome mapping, marks, type, expected response and provenance.
- **S06 — Question Bank Curation Skill:** retrieve, deduplicate, version and reuse approved questions without leaking protected assessment content.
- **S07 — Answer and Rubric Skill:** produce model answers, point-by-point rubrics, accepted alternatives and worked reasoning.
- **S08 — Examination Moderation Skill:** independently challenge and validate the paper, answer key, mark allocation, fairness and blueprint compliance.

### Visual skills
- **S09 — Visual Requirement Analysis Skill:** determine whether each topic/outcome needs a diagram, chart, map, schema, image or no visual.
- **S10 — Visual Generation Brief Skill:** create technically precise generation briefs and structured diagram specifications.
- **S11 — Visual Validation and Approval Skill:** check legibility, correctness, labels, source/licensing, accessibility and moderator approval before use.
- **S12 — Visual Question Design Skill:** write questions that genuinely assess interpretation, construction or application of the approved visual.

### Delivery and learning skills
- **S13 — Web Examination Assembly Skill:** generate valid semantic HTML, CSS and JavaScript with response widgets matched to question types.
- **S14 — Attempt and Submission Skill:** define secure attempt states, autosave, timer, resume, finalisation and immutable submission behaviour.
- **S15 — Objective Marking Skill:** produce deterministic scoring rules and tested answer comparisons.
- **S16 — Subjective Marking Assistance Skill:** apply approved rubrics, cite response evidence, express uncertainty and route uncertain cases to a human marker.
- **S17 — Performance Diagnosis Skill:** identify evidence-backed strengths and gaps from item-level outcomes.
- **S18 — Personalised Revision Skill:** create topic-targeted explanations, examples, recall exercises and spaced revision plans.
- **S19 — Academic PDF Authoring Skill:** produce complete, polished memorandums and revision guides using structured source content and approved visuals.
- **S20 — Python Engineering Skill:** design, implement, test, document and maintain Python services, schemas, migrations, APIs, workers and integrations.

## 6. Visual-first examination planning gate

The workflow must enforce this sequence whenever visuals may be academically required:

1. Analyse the subject taxonomy, source content and learning outcomes.
2. Identify topics/outcomes requiring a visual assessment or visual reference.
3. Search supplied material for suitable source visuals and record page/slide provenance.
4. Determine which visuals are missing, unsuitable, illegible or technically incorrect.
5. Generate only the missing visuals, using a structured brief and approved generation capability.
6. Validate each visual for technical correctness, legibility, labels, accessibility and consistency with source material.
7. Present visuals to the authorised reviewer for explicit approval or rejection.
8. Attach approved, versioned visuals to the assessment package.
9. Design and moderate questions against the approved visual.
10. Freeze the visual/question/blueprint versions used by the published examination.

A required visual that is awaiting approval blocks final publication. If no visual is academically necessary, record that decision and proceed without generating decorative assets. Never claim that an image was generated when the system has only produced a textual description.

## 7. Question interaction contract

The question schema must define a stable question type and corresponding response component.

| Question type | Student control | Marking approach |
|---|---|---|
| Multiple choice | Radio group | Deterministic |
| Dropdown choice | Select/dropdown | Deterministic |
| Multiple select | Checkboxes | Deterministic, configured partial-credit policy |
| True/False | Two-option control | Deterministic |
| Fill in the blank | Inline text input | Exact/normalised or accepted-answer rules |
| Short answer | Text box | Rubric/human review unless explicitly objective |
| Long answer/essay | Extended text editor | Rubric-assisted, human oversight |
| Numeric | Numeric input | Exact or configured tolerance/unit rules |
| Matching | Matching interface | Deterministic mapping |
| Ordering | Reorderable sequence | Deterministic sequence scoring |
| Programming | Code editor | Sandboxed tests and/or rubric; never execute untrusted code on the API host |
| Diagram interpretation | Approved visual plus response controls | Type-specific rubric or deterministic elements |
| Diagram construction | Safe drawing/structured editor | Rubric or validated structured output |

The UI must not infer the control from question wording. It must render from the validated question schema. Autosave and validation must preserve responses across navigation and reloads.

## 8. Examination workflow and state model

Recommended lifecycle:

`DRAFT → CONTENT_READY → VISUAL_REVIEW (if required) → BLUEPRINT_APPROVED → ASSEMBLED → MODERATION → APPROVED → PUBLISHED → OPEN → SUBMITTED → MARKED → RELEASED → REVISION_READY`

Use explicit rejected, revision-required, cancelled and archived states. State transitions must be authorised and audited. Published exams and attempts reference immutable versions of the blueprint, questions, visuals and marking scheme.

Practice and formal simulation are separate policies:
- Practice may reveal hints, answers and explanations according to configuration.
- Formal simulation must not expose answer keys or explanations in browser payloads before authorised release.
- Formal attempts require server-controlled start/end times, autosave, submission finality and access rules.
- Client-side timers are presentation aids; the server clock is authoritative.

## 9. Core data domains

At minimum, model:

- User, Role, Permission, Workspace
- Subject, Module, Topic, Subtopic, LearningOutcome
- SourceDocument, SourceVersion, ExtractedPassage, SourceCitation
- VisualAsset, VisualVersion, VisualApproval
- Blueprint, BlueprintConstraint, BlueprintOutcomeWeight
- Question, QuestionVersion, QuestionOption, QuestionProvenance
- AnswerKey, MarkingRubric, AcceptedAnswer
- Examination, ExaminationVersion, ExaminationQuestion
- Attempt, AttemptResponse, SubmissionEvent
- MarkingResult, MarkerReview, ModerationRecord
- StudentTopicMastery, AnalyticsSnapshot
- RevisionPlan, RevisionActivity, PDFExport
- AuditEvent, BackgroundJob

Use tenant/workspace-aware authorisation, foreign keys, uniqueness constraints, migration scripts, retention policies and appropriate indexes. Store source files and generated assets in object storage; store metadata and relationships in PostgreSQL.

## 10. API boundaries

Use versioned REST endpoints, documented with OpenAPI. Initial endpoint families:

- `/api/v1/auth/*`
- `/api/v1/sources/*`
- `/api/v1/subjects/*`
- `/api/v1/visuals/*`
- `/api/v1/blueprints/*`
- `/api/v1/questions/*`
- `/api/v1/examinations/*`
- `/api/v1/attempts/*`
- `/api/v1/submissions/*`
- `/api/v1/marking/*`
- `/api/v1/analytics/*`
- `/api/v1/revision/*`
- `/api/v1/exports/*`
- `/api/v1/admin/*`

Use idempotency keys for submission and export operations where retries could create duplicates. Enforce object-level access checks on every resource request. Never return answer keys, private rubrics or moderation notes to a student endpoint unless the release policy permits it.

## 11. Moderation and quality gates

### Pre-publication checks
- Source coverage and learning-outcome alignment.
- Topic and cognitive-level distribution against blueprint.
- Question clarity, bias, ambiguity and duplicate detection.
- Marks are positive, valid and sum exactly to the configured total.
- Duration is reasonable for the expected response effort.
- Every objective question has a valid key and valid option set.
- Written questions have usable marking rubrics.
- Calculations and worked solutions are independently checked where feasible.
- Required visuals are approved and correctly referenced.
- Answer key and memorandum match the final question versions.
- Accessibility, rendering and responsive behaviour pass.

### Post-submission checks
- Submission integrity and attempt identity.
- Objective scoring reproducibility.
- Rubric consistency and evidence traceability.
- Unanswered and invalid responses.
- Ambiguous or defective items flagged for moderation.
- Statistical item analysis only where sample size supports meaningful interpretation.

Moderation results must be recorded with severity, evidence, reviewer, resolution and timestamp. An AI-generated pass is not a substitute for an authorised human approval policy.

## 12. Marking and analytics requirements

- Objective marking is deterministic, server-side and repeatable.
- Accepted alternatives, case/whitespace normalisation, numeric tolerances, units and partial credit are explicit per question.
- Written marking uses approved criteria, criterion-level evidence, confidence and moderation status. Human review is required for low confidence, disputes and configured formal assessments.
- Record raw marks, moderated marks, marker identity, rubric version and change history.
- Analytics distinguish observed evidence from inferred mastery. Avoid presenting a single attempt as definitive mastery.
- Track topic/outcome performance, question difficulty, distractor selections, time spent and progress across attempts.
- Apply role-based access and aggregation thresholds to protect student privacy.

## 13. Personalised revision and PDF deliverables

After marking and release, create a revision profile from verified response evidence. Separate:
- **Memorise:** terminology, formulas, definitions and essential facts.
- **Understand:** principles, relationships and explanations.
- **Apply:** procedures, calculations and worked examples.
- **Analyse/evaluate:** scenarios, comparisons and justifications.
- **Create:** designs, models, diagrams and complete solutions.

Revision plans should prioritise high-impact knowledge gaps, include active recall and spaced retrieval, link back to source pages and generate new practice questions. Avoid claiming guaranteed exam predictions.

PDF outputs:
1. Examination paper (where requested).
2. Complete memorandum with accepted alternatives and worked solutions.
3. Examiner/marker guide with rubrics and moderation notes, access-controlled.
4. Student revision guide with in-depth topic notes, diagrams, examples, memory aids and common errors.
5. Personalised performance and revision report.

PDF generation must use Python and a maintained PDF library, preserve mathematical/technical layout, embed approved images, include page numbers and metadata, and be tested for readable extraction and rendering.

## 14. Python engineering standards

The Python Engineering Skill must:
- Follow typed, modular Python with clear service/repository boundaries.
- Validate all external input using Pydantic and domain rules.
- Keep provider clients behind adapters and secrets outside source control.
- Use database transactions and explicit state transitions.
- Make background tasks retry-safe and idempotent.
- Apply upload size/type limits, malware scanning where available and safe parsing.
- Treat prompt-injected instructions in uploaded content as untrusted data.
- Never execute uploaded code or generated code outside an isolated sandbox.
- Add unit, integration, API contract, migration and security tests.
- Provide reproducible setup, dependency locks, migrations and operational documentation.

## 15. Security, privacy and academic integrity

- Authentication and role-based access for students, lecturers, moderators and administrators.
- Object-level authorisation and workspace isolation.
- Encryption in transit and at rest where supported.
- Secrets stored only in deployment secret management.
- Rate limits, request-size limits, secure headers and audit logging.
- File validation, isolated parsing and retention/deletion controls.
- No student data or confidential source materials in public repositories or logs.
- No browser exposure of private keys, answer keys or unreleased rubrics.
- Formal exam policy must be configurable and transparent; do not promise impossible invigilation or cheating prevention.
- Provide accessible alternatives and accommodations without compromising assessment validity.

## 16. Delivery roadmap and acceptance criteria

### Phase 0 — Architecture and migration foundation
- Approve this plan and record decisions.
- Map current Next.js workspace and TypeScript Worker behaviour.
- Define API contracts, Python service layout, database model and migration plan.
- Create CI for Python and frontend; add test fixtures.
- No existing functionality is removed.

**Exit:** reviewed architecture, runnable Python API skeleton, health endpoint, CI and migration ADRs.

### Phase 1 — Persistent core and security
- Authentication/roles, PostgreSQL, migrations, workspace isolation, audit events.
- Server-side examination/attempt models and immutable versioning.

**Exit:** integration tests prove persistence, access isolation and idempotent attempt operations.

### Phase 2 — Academic ingestion and subject intelligence
- Document processing, OCR path, citations, taxonomy and classification review.

**Exit:** uploaded resources can be searched and traced to page/slide/source references; extraction failures are visible.

### Phase 3 — Blueprint, question bank and answer intelligence
- Blueprint constraints, reusable question lifecycle, provenance, deduplication and rubrics.

**Exit:** a blueprint can be satisfied by approved questions; marks and outcome coverage validate.

### Phase 4 — Visual intelligence and moderation
- Visual requirement analysis, generation adapter, approval workflow and moderation report.

**Exit:** required visuals block publication until approval; all moderation findings are traceable.

### Phase 5 — HTML/CSS/JS examination delivery
- Versioned exam package, all required question controls, accessible responsive interface, timer and autosave.

**Exit:** browser tests cover every question type, navigation, refresh recovery and formal answer-key non-disclosure.

### Phase 6 — Submission and marking
- Server-authoritative timing, final submission, deterministic objective scoring and rubric-assisted subjective marking.

**Exit:** repeatable scoring, immutable submissions, duplicate-submit protection and human review paths.

### Phase 7 — Analytics and personalised revision
- Topic analysis, performance dashboard, adaptive practice and spaced revision.

**Exit:** revision recommendations link to actual incorrect/weak outcomes and can be regenerated from stored results.

### Phase 8 — PDF production
- Memorandums, examiner guides and student revision packs.

**Exit:** generated PDFs pass content, rendering, extraction, page-layout and access-control tests.

### Phase 9 — Production hardening
- Load/security/accessibility tests, backups, monitoring, disaster recovery and deployment documentation.

**Exit:** release checklist passed and operational ownership documented.

## 17. Repository migration strategy

Current inspected baseline contains a Next.js/React/TypeScript workspace, a TypeScript Cloudflare Worker, Docker configuration, GitHub Pages/Worker workflows and documentation. Preserve this baseline.

Migration rules:
1. Keep the current workspace functional while the Python API is developed.
2. Build the Python API as a separately deployable service with documented contracts.
3. Move provider calls and business logic into Python behind provider adapters.
4. Update the frontend to call the Python API only after contract and integration tests pass.
5. Convert generated student exam output to HTML/CSS/JS packages as a first-class publishing target.
6. Retain the TypeScript Worker temporarily only if required for a controlled transition; remove/decommission it after verified traffic cutover and no remaining dependencies.
7. Update Docker, CI/CD, environment examples and deployment docs only alongside tested migration steps.
8. Never commit secrets, real student records or private academic documents.

## 18. Definition of done

EXAMGEN AI reaches the target platform state when a permitted user can:

1. Import academic resources and verify extracted content.
2. Build or approve a subject/module/topic/learning-outcome structure.
3. Configure a blueprint with marks, duration, question types and cognitive levels.
4. Have the system identify required visuals, generate/retrieve them, obtain approval and attach them.
5. Assemble a reusable, provenance-aware question set.
6. Generate answer keys and rubrics and pass moderation.
7. Publish a responsive HTML/CSS/JS examination website with appropriate response controls.
8. Run practice and formal simulations with secure, persistent attempts.
9. Submit and retrieve responses reliably.
10. Receive deterministic objective marks and appropriately reviewed subjective marks.
11. View meaningful performance analytics and topic-level gaps.
12. Generate personalised revision activities and professional PDF deliverables.
13. Audit the versions, source provenance and moderation decisions for every published examination.

**Current status:** This is the approved target plan. The repository's existing release remains a foundation; the modules and acceptance criteria above are future implementation work until code and tests demonstrate otherwise.


## 19. Student coursework resource experience (binding product requirement)

Academic ingestion is a student-facing capability embedded in the subject/module coursework workspace. It is not a standalone ingestion portal and must not be presented as a separate administrative product. From the relevant coursework page, a student can upload a file or scan a resource using the device-supported capture flow. Supported resources include lecture notes, slides, prescribed readings, worksheets, diagrams and prior assessments. The system then validates and scans the file, extracts text and structure, performs OCR when required, retains source/page/slide provenance, and exposes processing status and usable extracted content in that same subject context.

**Ownership and access rules:**
- Every resource is linked to a canonical subject/module and records its uploader and immutable versions.
- Default visibility is private to the uploader. Sharing with a class or cohort requires an explicit coursework-level sharing policy and authorised action.
- Students can create resources, view their own resources, append their own versions, inspect processing status and access their own extracted segments.
- Students cannot alter canonical subject/topic/learning-outcome taxonomy, approve/reject extraction quality, override classification, or access examiner-only moderation history.
- Authorised lecturers/examiners/moderators can review resources according to workspace and coursework permissions; staff decisions are append-only and audited.
- Every list, detail, version, segment, storage and download operation performs object-level authorization. A workspace membership alone must never expose another student's private resource.
- Resource processing is asynchronous and retry-safe. A failed scan/extraction is visible with a safe reason and retry/recovery path; it must never silently appear as usable academic content.

**Acceptance tests:** student upload from a subject page; scanned/image-only PDF OCR; upload status transitions; same-student version append; another student's private-resource access denied; wrong-subject access denied; explicitly shared cohort resource visible only to eligible members; taxonomy and examiner-review endpoints remain staff-only; audit/provenance retained across versions; frontend browser tests cover upload, scan, progress, retry and accessibility.

This requirement changes the authorization model from the current staff-only workspace document routes. Implementation must add subject/module association and explicit resource ownership/sharing without weakening existing tenant isolation or exposing answer keys and moderation data.
