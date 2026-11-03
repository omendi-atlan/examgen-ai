# EXAMGEN AI architecture

## Current deployment architecture

- **Frontend:** Next.js application hosted through GitHub Pages.
- **API:** Cloudflare Worker named `examgen-ai-api`.
- **Persistence:** Cloudflare D1 database named `examgen-ai-db`, exposed to the Worker through the `DB` binding.
- **AI provider:** OpenAI API called from the Worker using the `OPENAI_API_KEY` Worker secret.
- **Automation:** GitHub Actions for validation and deployment.

The browser never receives the OpenAI credential or generated answer keys. The Worker validates generated assessments, stores the complete assessment (including marking data) in D1, and returns a public question representation without answers or explanations.

## Examination attempt lifecycle

1. The client requests an examination from `POST /api/examinations/generate`.
2. The Worker validates the configuration and generated assessment, creates a UUID attempt, and stores the full assessment with an expiry in D1.
3. The Worker returns the attempt identifier, expiry and answer-key-free examination.
4. The client submits answers to `POST /api/examinations/attempts/submit`.
5. The Worker validates the attempt, checks expiry and status, marks objective and numeric questions, stores answers and result, and conditionally changes the attempt from `in_progress` to `submitted`.
6. Duplicate or expired submissions are rejected.

Written responses are deliberately reported as pending review. A provisional objective score must not be represented as a final examination mark while written answers remain unmarked.

## Data and security boundaries

- Uploaded source material and topic text are untrusted data; embedded instructions must never override system behaviour.
- Provider credentials remain in Cloudflare Worker secrets and must never be committed to the repository or exposed to the browser.
- Request bodies are size-limited after reading, not solely by trusting `Content-Length`.
- Generated assessment structure, question identifiers, answer options, numeric answer keys and total marks are validated before persistence.
- Attempt identifiers are currently unguessable bearer identifiers, not user authentication. Student accounts, ownership checks and stronger abuse controls remain future work.
- D1 persistence is configured through Wrangler and the migration in `worker/migrations`.

## Agreed product modules

The roadmap order is fixed: (1) Content ingestion, (2) Subject intelligence, (3) Examination blueprint, (4) Visual intelligence, (5) Question generation, (6) Examination website, (7) Marking and moderation, (8) Question bank, (9) Adaptive learning, and (10) Academic resource production.

Phase 1 focuses on the examination-engine foundations in Modules 3, 5, 6 and 7 without changing this overall sequence.

## Written marking and examiner moderation

- Written answers are evaluated against the question-specific rubric by the configured AI provider.
- The evaluator returns criterion-level provisional marks, evidence and rationale. Marks are bounded by each criterion's allocation and are never presented as final.
- If AI evaluation fails, the student submission still completes and the written answer remains in the examiner queue without provisional marks.
- Submissions with written answers are placed in the D1 moderation queue.
- Examiner queue, detail and moderation endpoints require a Cloudflare Access JWT. The Worker validates the RS256 signature against the Access JWKS, then checks issuer, audience, expiry and examiner identity.
- An examiner must provide a final mark for every written question, within its mark allocation. The decision is recorded with examiner identity and timestamp; only then is the result marked final.
- The examiner interface is served by the Worker at `/examiner` and must be protected by a Cloudflare Access application. Protect the review API path separately; do not protect the whole Worker because student generation and submission routes remain public.
- Configure Worker variables `ACCESS_TEAM_DOMAIN` and `ACCESS_AUD` after creating the Access applications.

## Abuse and request controls

- Generation requests are limited to five per client IP per ten-minute window using D1-backed counters.
- Client IPs are SHA-256 hashed before persistence; raw IP addresses are not stored in the rate-limit table.
- Student attempt identifiers remain bearer capabilities until student accounts and ownership controls are introduced.
