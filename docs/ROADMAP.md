# EXAMGEN AI — Integrated implementation roadmap

**Canonical plan:** seven delivery phases, ten functional modules, no mandatory external AI provider.  
**Completion policy:** a phase is complete only when its acceptance criteria pass and the deployed behaviour has been verified where deployment is authorised.

## Product outcome

EXAMGEN AI is an examination creation, administration, assessment and adaptive-learning platform. It ingests academic material, organises subjects and topics, builds examinations from configurable blueprints and a reusable question bank, delivers practice and simulation assessments, marks responses, analyses performance, and produces professional academic resources.

The application must operate without an OpenAI key, paid AI API, VPS or custom domain. Automated functions must use deterministic rules, approved content, templates and explicit human review. No deterministic keyword matcher may be represented as semantic understanding.

## Fixed functional module order

1. **Content ingestion** — import PDF, DOCX, text and previous examination material; extract, review, correct and approve content.
2. **Subject intelligence** — manage subjects, topics, concepts, learning outcomes and syllabus coverage through explicit, editable classification.
3. **Examination blueprint** — configure duration, marks, topic weighting, question types, difficulty, cognitive demand and sections.
4. **Visual intelligence** — identify visual requirements, upload/manage diagrams and charts, associate assets with questions, and require approval before publication.
5. **Question generation** — author questions, use structured/parameterised templates, and assemble papers from approved question-bank entries under blueprint constraints. No external LLM is required.
6. **Examination website** — configure, take, save, submit and review practice examinations and formal simulations.
7. **Marking and moderation** — mark objective/numeric questions deterministically; support criterion rubrics and manual marking for written responses. Written marks requiring judgement remain pending until reviewed.
8. **Question bank** — persist, classify, search, version, archive, reuse and track provenance for questions and marking guides.
9. **Adaptive learning** — analyse actual attempt results, identify weak topics and recurring errors, recommend revision priorities, and adjust practice difficulty using transparent rules.
10. **Academic resource production** — generate accessible, consistently formatted examination papers, memoranda, examiner notes, topic summaries and revision PDFs from approved content.

## Seven delivery phases

### Phase 1 — Core infrastructure and reliable examination engine
**Scope:** deployment foundation, D1 persistence, attempt lifecycle, server-side objective marking, written-answer rubric storage/manual assessment foundations, validation, rate limiting and security.

Actions:
- Remove OpenAI SDK, API calls, model configuration, key requirements, provider-specific errors and AI-marking claims.
- Replace AI question generation with validated, user-authored/approved question payloads and bank-backed assembly as those modules arrive.
- Persist attempts, examination snapshots, answers and results in D1.
- Keep answer keys and rubrics server-side.
- Validate question IDs, types, answer formats, total marks, rubric allocations and expiry.
- Enforce one-time submission, expiry and safe retry semantics.
- Mark MCQ, dropdown and numeric answers deterministically; support configured numeric tolerance.
- Store written answers as pending manual/rubric assessment; do not fabricate marks.
- Apply D1-backed generation throttling and request size limits.
- Run unit, integration, typecheck, lint and build tests.

Acceptance:
- Create, load, save, submit and retrieve a persisted attempt.
- Timer and auto-submit work; expired and duplicate submissions are rejected.
- Objective marking and result totals are correct, including numeric tolerance.
- Written responses remain explicitly pending until assessed.
- Browser payloads never expose answers, explanations or marking rubrics.
- Migrations apply cleanly; all CI checks pass; live Pages-to-Worker-to-D1 workflow is verified after separately authorised deployment.

### Phase 2 — Application foundation and academic workspace
**Scope:** coherent navigation and workspace for all modules.

Actions:
- Build dashboard and application shell.
- Add subject/topic workspace, content library, question bank, blueprint builder, exam builder, practice/simulation, results, resources and settings navigation.
- Build reusable form, table, status, modal, upload, preview and empty-state components.
- Add responsive desktop/tablet/mobile layouts and accessible keyboard/focus behaviour.
- Connect dashboard summaries to persisted records; do not show fabricated metrics.

Acceptance:
- Every navigation destination is functional or clearly marked as not yet available.
- Forms validate; empty/loading/error states are complete.
- Subject and topic records can be created, edited and archived.
- Responsive and accessibility smoke tests pass.

### Phase 3 — Content ingestion and subject intelligence (Modules 1–2)
Actions:
- Upload and validate supported PDF, DOCX, TXT and Markdown files with size/type limits.
- Extract text and preserve page/section provenance where technically available.
- Provide extraction preview, correction, approval and rejection workflows.
- Detect candidate questions, options, answers, instructions and marking guides using deterministic patterns; never silently assume extraction is correct.
- Manage subject → topic → subtopic → concept hierarchies.
- Manage learning outcomes and map content/questions to them.
- Track syllabus coverage, source citations and classification confidence/verification status.
- Permit manual classification and correction.

Acceptance:
- Supported documents upload, extract, preview, correct and persist.
- Unsupported, malformed and oversized files are rejected safely.
- Extracted items retain source provenance.
- Subjects, topics, outcomes and mappings persist and can be edited.
- Unreviewed extraction is not treated as approved examination content.

### Phase 4 — Blueprint, visual intelligence and question assembly (Modules 3–5)
Actions:
- Build blueprint editor for marks, duration, sections, topic weighting, difficulty, cognitive demand and question types.
- Validate weighting totals, marks totals, question counts and blueprint feasibility.
- Build visual asset upload/library, question association, alt text/captions and approval status.
- Flag questions that require a diagram/chart and block publication until resolved or explicitly waived.
- Build manual question authoring and reusable templates, including parameterised numeric questions where safe.
- Assemble exams from approved question-bank content while satisfying blueprint constraints.
- Add deterministic randomisation, duplicate prevention, versioning and full preview.

Acceptance:
- Invalid or impossible blueprints are blocked with actionable messages.
- Assembled papers meet marks/topic/type/difficulty constraints or report why they cannot.
- Only approved questions and approved visuals enter a published paper.
- Answer keys remain private and question provenance is retained.

### Phase 5 — Examination delivery and assessment (Modules 6–7)
Actions:
- Complete practice and formal simulation workflows.
- Support MCQ, dropdown, numeric, short-answer and long-answer controls.
- Add instructions, sections, navigation, progress, review-before-submit, timer, autosave and automatic submission.
- Implement objective marking, accepted-answer sets, numeric tolerance and configured partial marks.
- Implement rubric criteria/descriptors and a manual marking workspace with criterion-level scores, feedback, marker and timestamp.
- Clearly separate automatically marked, pending, provisionally assessed and finalised results.
- Preserve marking history and prevent unauthorised alteration of submitted attempts.

Acceptance:
- Full attempt lifecycle works across refreshes and transient network errors.
- Objective results match test fixtures exactly.
- Written answers can be assessed against rubric criteria by a human workflow.
- Unreviewed written answers never receive invented final marks.
- Practice feedback and simulation result disclosure obey their configured modes.

### Phase 6 — Question bank, adaptive learning and academic resources (Modules 8–10)
Actions:
- Build persistent question bank with subject/topic/type/difficulty/cognitive-level filters.
- Track provenance, versions, approvals, usage, archive state and duplicate candidates.
- Analyse attempt results by topic, outcome, difficulty and question type.
- Identify weak areas only where enough attempt evidence exists; show sample size and method.
- Recommend revision priorities using transparent score thresholds and recency rules.
- Adjust future practice difficulty using documented deterministic rules.
- Produce revision plans and progress reports from actual results.
- Generate examination papers, memoranda, examiner notes, topic summaries and revision PDFs from approved records.
- Add print styles, page numbers, headings, tables, accessible contrast and export validation.

Acceptance:
- Question bank CRUD/search/version/provenance works.
- Analytics reconcile to stored attempts and marks.
- Revision recommendations are explainable and reproducible.
- PDFs render correctly and include only approved content.
- Examination paper and memorandum totals and question numbering reconcile.

### Phase 7 — System-wide verification and operational readiness
Actions:
- Run full end-to-end journey from document upload through PDF export.
- Run security, accessibility, performance, file-handling, concurrency and regression tests.
- Verify CORS, rate limits, payload limits, secret hygiene, D1 constraints and error handling.
- Verify migrations, backup/export and recovery procedures.
- Verify GitHub Actions, Pages deployment and Worker deployment.
- Add monitoring/health checks and operational documentation.
- Produce user guide, admin/maintenance guide, data dictionary and release notes.

Acceptance:
- All ten modules pass their phase-specific tests.
- Full end-to-end acceptance scenario passes without any AI-provider credential.
- No critical/high-severity defects remain open.
- Production deployment and live smoke tests are verified only after explicit deployment approval.
- Documentation accurately describes delivered functionality and known limitations.

## Cross-cutting requirements

- **No mandatory AI provider:** no API key, model endpoint, billing dependency or AI-only feature may block core workflows.
- **Truthful automation:** deterministic rules must be labelled as such; human judgement remains human review.
- **Data protection:** server-side answer keys/rubrics, input validation, safe file handling, rate limiting and no secrets in client bundles.
- **Traceability:** source provenance for imported content, version history for questions/exams, and audit history for marking.
- **Persistence:** D1 is authoritative for records; browser state is not the only copy of an attempt.
- **Accessibility:** keyboard support, semantic labels, readable feedback and print-friendly output.
- **No student accounts in this release:** anonymous attempt IDs are temporary bearer capabilities, not authentication. Add identity/ownership only as a separately scoped future phase.
- **No examiner Access/audience configuration in this release:** manual marking UI and workflow must not assume Cloudflare Access or institutional email setup.

## Phase status vocabulary

- Not started — no implementation.
- In progress — work underway.
- Implemented — code exists; acceptance not complete.
- Verified — all applicable tests and acceptance evidence pass.
- Deployed — authorised release is live and smoke-tested.
- Complete — all phase gates pass and evidence is recorded.

A passing build alone never makes a phase complete.

## End-to-end acceptance scenario

1. Upload a previous paper and learning material.
2. Extract, review and approve source content.
3. Organise subjects, topics and learning outcomes.
4. Configure a blueprint.
5. Upload/link and approve required visuals.
6. Assemble a paper from approved bank questions.
7. Preview and publish it.
8. Complete a practice examination and a formal simulation.
9. Persist answers and submit each attempt.
10. Mark objective responses and manually assess written responses using rubrics.
11. Analyse results and identify weak topics.
12. Produce explainable revision recommendations.
13. Export examination paper, memorandum and revision PDF.

The entire journey must work without an external AI service.
