# Question bank and blueprint-driven generation

## Scope

The question bank is a canonical Python/PostgreSQL feature. A question has a stable identity and append-only content versions. Every version is linked to an explicit subject topic, learning outcome and one or more immutable extracted source segments.

AI generation creates **private draft questions** for the requesting workspace member. It does not publish questions automatically. Authorised staff may approve a version for cohort use after checking its content and provenance.

## Security and disclosure

- Student list/detail/generation responses never include `answer_key`, `model_answer`, `explanation` or `rubric`.
- The authoring endpoint that returns marking material is restricted to staff roles.
- Private questions are visible only to their creator and authorised staff.
- Cohort questions are visible to students only after a staff member approves the current version.
- Cohort questions may cite only subject resources explicitly shared with that cohort.
- A source must be in the same workspace and subject, have completed extraction, and not have a latest rejected extraction decision.
- Every citation retains its source segment ID, immutable source version ID, original locator and excerpt.
- A duplicate content fingerprint in the workspace is rejected rather than silently adding a duplicate question.

## Generation contract

Generation requires an approved blueprint version and selected, accessible, successfully extracted source versions. The server sends source material to the configured provider as untrusted data and explicitly instructs the model to ignore embedded instructions.

The provider response is validated before any question is persisted. Synchronous generation is capped at 30 questions per request and 10 requests per account per hour:
- exact question count and total marks;
- exact topic and learning-outcome mark allocations;
- integer mark allocations derived deterministically from cognitive, difficulty and question-type percentages;
- type-specific response and answer-key structure;
- written/programming rubrics whose criterion marks sum to the question marks;
- citations restricted to selected source segments.

Invalid, incomplete or out-of-blueprint output is rejected without saving draft questions. Provider credentials are read only from server environment settings (`OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS`). No API key is returned to a client or stored in the database.

## API

- `POST /api/v1/workspaces/{workspace_id}/questions`
- `GET /api/v1/workspaces/{workspace_id}/questions`
- `GET /api/v1/workspaces/{workspace_id}/questions/{question_id}`
- `GET /api/v1/workspaces/{workspace_id}/questions/{question_id}/authoring` (staff only)
- `POST /api/v1/workspaces/{workspace_id}/questions/{question_id}/versions`
- `POST /api/v1/workspaces/{workspace_id}/questions/{question_id}/versions/{version_id}/approve` (staff only)
- `POST /api/v1/workspaces/{workspace_id}/blueprints/{blueprint_id}/versions/{blueprint_version_id}/generate-questions`

## Current limitations

- Generation is a bounded synchronous provider request (10–120 second configured timeout, 45 seconds by default); a durable generation-job queue and cancellation/progress UI remain future work.
- Diagram questions are stored with a visual requirement brief but cannot be approved until the visual asset review workflow exists.
- Objective scoring, formal examination assembly, student attempt persistence and practice simulation are the next delivery phase.
- Real provider qualification requires `OPENAI_API_KEY` in deployment secret management. CI uses a deterministic mocked provider and never requires a real key.
