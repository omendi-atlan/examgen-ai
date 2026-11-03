# EXAMGEN AI — ten functional modules

The product roadmap is organised into these ten modules in this exact order:

1. **Content ingestion** — import PDFs, DOCX files, text documents and previous tests; extract, preview, correct and approve content with source provenance.
2. **Subject intelligence** — explicitly classify subjects, topics, subtopics, concepts, learning outcomes and syllabus coverage.
3. **Examination blueprint** — configure marks, topic weightings, duration, question types, difficulty, cognitive demand and sections.
4. **Visual intelligence** — identify visual requirements, upload and manage diagrams/charts, link assets to questions and require approval before publication.
5. **Question generation** — author questions, use deterministic templates and assemble papers from approved question-bank content under blueprint constraints. No external AI provider is required.
6. **Examination website** — configure, take, save, submit and review practice examinations and formal simulations.
7. **Marking and moderation** — automatically mark objective/numeric questions; assess written answers using explicit rubrics and manual marking. Unreviewed written answers remain pending.
8. **Question bank** — persist, classify, search, version, archive, reuse and track question provenance and usage.
9. **Adaptive learning** — analyse recorded performance, identify weak topics and recurring errors, and recommend revision/difficulty changes using transparent rules.
10. **Academic resource production** — produce examination papers, memoranda, examiner notes, topic summaries and revision PDFs from approved content.

## Implementation discipline

The ten modules are the fixed functional scope. Their implementation is delivered through seven phases documented in [the integrated roadmap](../docs/ROADMAP.md). A module is not complete merely because its interface or database table exists: it must pass its acceptance tests and work in the integrated application.

## Product constraints

- No mandatory OpenAI or other external AI provider, API key, model endpoint or AI billing.
- Deterministic automation must be clearly distinguished from human judgement.
- No semantic-marking claims for keyword matching.
- Student accounts and examiner-specific Cloudflare Access configuration are deferred.
- Anonymous attempt identifiers are temporary bearer capabilities, not authentication.
