# Examination Intelligence Plugin (EIP)

**Status:** Specification approved; implementation not yet qualified  
**Initial version target:** 0.1.0  
**Parent platform:** EXAMGEN AI  
**Deployment model:** Independently versioned module integrated through documented adapters

## Purpose

EIP transforms resources uploaded for one selected subject/module into a validated examination blueprint, reusable question set, interactive examination configuration, marking package and targeted learning resources.

EIP is a standalone application module/plugin. It is not a claim that a distributable ChatGPT connector or marketplace plugin has been published.

## Non-negotiable compatibility rules

- Preserve the current student workspace and its subject/topic configuration.
- Preserve existing practice and formal-simulation modes.
- Preserve the current generation endpoint contract unless a versioned adapter or migration is approved.
- Preserve objective scoring behaviour and current mark-total validation.
- Keep the existing deployment, Docker and CI workflows operational.
- Do not introduce mandatory student accounts as a prerequisite for the core workflow.
- New capabilities must be additive, independently testable and feature-gated until qualified.

## Student journey

1. Student selects one subject/module and uploads only its relevant resources.
2. Ingestion validates files and extracts content without executing or obeying embedded instructions.
3. Subject intelligence builds a source-traceable topic and learning-outcome model.
4. Visual requirements are assessed before the first blueprint is finalised.
5. Required visuals are generated/retrieved, technically reviewed and explicitly approved before use.
6. Blueprint engine distributes marks, topics, difficulty and cognitive demand.
7. Question bank assembles unique, markable, traceable questions.
8. Exam delivery adapter renders a responsive website with controls appropriate to each question type.
9. Attempt service saves answers, submits attempts and protects formal-simulation answer keys.
10. Marking service scores objective answers and applies explicit rubrics; uncertain written responses are routed for human review.
11. Export service generates two separate PDFs: an examination memorandum and an examination mastery study guide.
12. Learning analytics reports topic performance and recommends targeted practice.

## Core capabilities and contracts

| Capability | Required input | Required output | Release gate |
|---|---|---|---|
| Resource ingestion | Subject-scoped files | Validated extracted content and source IDs | File safety and extraction tests |
| Subject intelligence | Extracted content | Topics, outcomes, concepts and provenance | Coverage and traceability tests |
| Visual gate | Subject model and assessment intent | Visual-needed decision and requirements | No blueprint finalisation before gate |
| Visual approval | Candidate assets | Approved/rejected asset records and provenance | Technical review and explicit approval |
| Blueprint | Subject model and exam constraints | Reconciled exam blueprint | Marks, time and coverage validation |
| Question bank | Blueprint and source model | Classified, unique question records | Scope, ambiguity and markability tests |
| Exam delivery | Approved paper | Responsive exam session | Input, navigation and persistence tests |
| Marking | Submitted answers and rubric | Marked result with rationale/confidence | Deterministic objective and human-review tests |
| PDF export | Approved paper and marking model | Two complete, separate PDFs | Completeness and consistency tests |
| Learning analytics | Persisted attempts | Topic insights and practice priorities | Evidence-based reporting tests |

## Supported assessment interaction types

- Multiple-choice: selectable options.
- Dropdown: constrained selection for classification, matching and structured selection.
- Fill-in-the-blank: single-line text input.
- Short answer: multiline text box.
- Long answer/essay: large text editor.
- True/false: two-option selection.
- Matching: accessible matching controls.
- Calculations: working and final-answer fields.
- Diagram labelling and interpretation: approved embedded visual plus answer controls.
- Structured questions: multiple response fields grouped under one parent question.

Do not force every question into a dropdown. Use the interaction that accurately represents the assessment task.

## Question record minimum

Every question must carry a stable ID, prompt, subject/topic/subtopic, learning outcome, cognitive level, difficulty, mark allocation, response type, source references, marking criteria, moderation status and optional visual references.

Answer keys and explanations must remain server-side for formal simulation.

## Blueprint minimum

The blueprint records subject/module, source set, learning outcomes covered, sections, question IDs, topic weighting, cognitive-level weighting, difficulty distribution, duration, total marks and validation results. The sum of question marks must equal the declared paper total.

## PDF deliverables

### A. Examination memorandum

Complete question references, correct/model answers, mark allocations, rubrics, acceptable alternatives, partial-credit rules, worked calculations and visual interpretations.

### B. Examination mastery study guide

In-depth explanations, essential knowledge, definitions, memorisation versus understanding guidance, application methods, worked examples, memory aids, common mistakes, examination-answering strategies and evidence-based revision priorities.

Do not describe inferred examiner preferences or confidential moderation practices as verified facts. Clearly label source-verified criteria, reasonable inferences and recommendations.

## Service boundaries

Keep domain logic independent of Next.js UI components and provider-specific SDKs. Use adapters for:
- AI model/provider access.
- File extraction.
- Image generation/retrieval and review.
- Persistence and attempt storage.
- PDF rendering.
- Authentication/authorization.

All provider secrets remain server-side. Uploaded documents are untrusted input. Enforce file limits, access controls, rate limits, auditability and safe error handling before production.

## Feature flags and rollout

Every capability is disabled or non-disruptive by default until its acceptance tests pass. Enable capabilities progressively: subject intelligence, visual gate, blueprint, question bank, exam delivery integration, marking, PDF exports, then learning analytics.

## Definition of done

EIP 0.1.0 is eligible for plugin qualification only when:
1. Its module boundaries and versioned contracts are implemented.
2. All mandatory acceptance tests pass with recorded evidence.
3. Existing platform regression tests pass.
4. Security, privacy and accessibility reviews are complete.
5. PDF and visual output checks pass.
6. Integration and rollback procedures are documented.
7. No planned capability is represented as completed without implementation evidence.
