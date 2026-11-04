# Examination blueprint foundation

## Scope delivered

The blueprint foundation creates an authorable, versioned assessment design. It does not yet generate questions or claim that a blueprint has been satisfied by a question bank.

Each blueprint has a stable workspace-scoped identity and append-only version snapshots. A version records:

- Subject and title/description.
- Duration, total marks and question count.
- Cognitive-level distribution (remember, understand, apply, analyze, evaluate, create).
- Difficulty distribution (easy, medium, hard).
- Question-type distribution from the supported examination response contract.
- Exact mark allocations across topics.
- Exact mark allocations across explicit learning outcomes.
- Draft/approved status, author, approver and approval timestamp.

Percentages in each distribution must total exactly 100. Topic allocations and learning-outcome allocations must each total exactly the configured examination marks. Topic and outcome identifiers must belong to the selected subject and workspace.

## API

- `POST /api/v1/workspaces/{workspace_id}/taxonomy/topics/{topic_id}/learning-outcomes`
- `GET /api/v1/workspaces/{workspace_id}/taxonomy/topics/{topic_id}/learning-outcomes`
- `POST /api/v1/workspaces/{workspace_id}/blueprints`
- `GET /api/v1/workspaces/{workspace_id}/blueprints`
- `GET /api/v1/workspaces/{workspace_id}/blueprints/{blueprint_id}`
- `POST /api/v1/workspaces/{workspace_id}/blueprints/{blueprint_id}/versions`
- `POST /api/v1/workspaces/{workspace_id}/blueprints/{blueprint_id}/versions/{version_id}/approve`

Authoring is restricted to workspace owners, administrators, examiners and moderators. Approval is restricted to owners, administrators and moderators. Every creation and approval is audited. Existing version content is never edited; changes require a new version.

## Integrity and limitations

- PostgreSQL stores the canonical blueprint, version, topic-allocation and outcome-allocation records.
- Database constraints enforce positive ranges, unique version numbers and unique topic/outcome allocations.
- Pydantic and service validation enforce exact distribution and mark totals and workspace/subject taxonomy membership.
- Approval is a human workflow decision on the blueprint design only. It does not mean questions have been generated, selected, validated or moderated.
- The next question-bank milestone must link approved question versions to blueprint versions and prove that question marks, topic coverage, outcome coverage, cognitive levels, difficulty and question types satisfy these constraints before assembly can proceed.
