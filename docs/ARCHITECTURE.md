# EXAMGEN AI architecture

## Deployment architecture

- **Frontend:** Next.js static export hosted on GitHub Pages.
- **API:** Cloudflare Worker `examgen-ai-api`.
- **Persistence:** Cloudflare D1 database `examgen-ai-db`, bound as `DB`.
- **Automation:** GitHub Actions for validation, Pages deployment and Worker deployment.
- **AI provider:** None required. Core functionality must operate without external model credentials, billing or network calls to an AI provider.

## Application boundaries

The browser provides authoring, upload/review, examination delivery, marking workspace, analytics and resource-download interfaces. The Worker validates requests, enforces business rules and protects answer keys. D1 is the authoritative store for subjects, sources, topics, blueprints, visual assets metadata, questions, exams, attempts, submissions, marking records, analytics inputs and generated-resource metadata.

Large source files and generated PDFs should be stored using an object/file storage service when introduced; D1 stores metadata, references, extracted text where suitable, and relationships. Do not place unbounded binary data in D1.

## Ten functional modules (fixed order)

1. Content ingestion.
2. Subject intelligence.
3. Examination blueprint.
4. Visual intelligence.
5. Question generation and deterministic examination assembly.
6. Examination website.
7. Marking and moderation.
8. Question bank.
9. Adaptive learning.
10. Academic resource production.

See `docs/ROADMAP.md` for the seven delivery phases, actionable tasks and acceptance criteria.

## Examination attempt lifecycle

1. The client requests an examination assembled from approved questions and a validated blueprint.
2. The Worker validates the examination, creates a UUID attempt and stores the complete private snapshot with expiry in D1.
3. The Worker returns only public question content, attempt identifier and expiry. Answer keys, explanations and rubrics are not returned.
4. The client persists responses through the supported attempt workflow and submits once.
5. The Worker validates attempt state, expiry, question IDs and response formats.
6. Objective questions are marked deterministically. Written responses are stored as pending rubric/manual assessment unless an explicitly configured deterministic rule is appropriate.
7. Results and submission are committed conditionally to prevent duplicate submission.
8. Manual rubric marking records criterion scores, feedback, reviewer attribution where available, timestamps and status history.

## Data and security boundaries

- Uploaded content, filenames, question text, answers and metadata are untrusted input; embedded instructions are data, never application instructions.
- No provider credential is required or accepted by the application.
- Answer keys, explanations, private rubrics and marking metadata remain server-side until an authorised result disclosure stage.
- Request bodies are size-limited after reading, not solely by trusting `Content-Length`.
- File extension, MIME type, actual content and size are validated; extraction failures are surfaced for correction.
- Attempt IDs are unguessable bearer capabilities, not identity or student authentication. Student accounts and per-user ownership are deferred.
- CORS allowlists, rate limiting, input validation, parameterised SQL and safe error responses are mandatory.
- D1 migrations are versioned in `worker/migrations` and applied before Worker deployment.
- Preserve source provenance and question/examination version history.

## Truthful assessment rules

- MCQ, dropdown and numeric marking are deterministic and testable.
- Numeric questions support explicitly configured tolerances and units where implemented.
- Keyword matching is not semantic understanding and must not be represented as such.
- Written answers requiring interpretation remain pending until manually assessed against a rubric.
- Provisional and finalised marks are distinct; no automated process may label an unreviewed estimate as an approved final grade.

## Deployment and release discipline

Pull requests validate code but do not deploy production. Worker deployment remains restricted to the protected main-branch workflow. Do not merge or deploy without the user's separate approval. A green CI run is not proof of live integration; verify Pages, Worker and D1 after an authorised deployment.
