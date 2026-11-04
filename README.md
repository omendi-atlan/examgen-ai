# EXAMGEN AI

An academic examination generation, simulation, visual assessment and subject
mastery platform. A student selects a single subject or module, uploads only
that subject's coursework, and receives a moderated examination, an interactive
examination website, accurate marking, and two PDF deliverables.

Every subject keeps its own isolated workspace: documents, extracted content,
topics, learning outcomes, visuals, blueprints, examinations, attempts, marking
records and PDFs. Content from one subject is never mixed into another.

## Capabilities

- **Subject-scoped resource management** — create independent subject
  workspaces and upload coursework (PDF, DOCX, PPTX, XLSX, CSV, text, HTML,
  images). Each workspace stores its own documents, versions and provenance.
- **Document intelligence** — extraction, heading/section detection, duplicate
  and conflict detection, and a resource-sufficiency report that names what is
  missing rather than inventing content.
- **Topic intelligence** — a Subject → Topic → Subtopic → Learning Outcome →
  Question hierarchy derived only from the uploaded material.
- **Visual assessment gate** — decides whether diagrams are essential,
  beneficial or unnecessary, then constructs editable SVG assets (flowcharts,
  ER diagrams, network topologies, UML, mathematical graphs, data tables and
  more). Assets are versioned and require approval before use.
- **Blueprint-driven generation** — configurable title, marks, duration,
  question count, difficulty (beginner → expert) and Bloom's taxonomy coverage.
- **Question bank** — fill-in-the-blank (text box), short answer, extended
  response, single choice (dropdown), multiple choice (checkboxes), matching,
  numerical, formula, ordering, diagram interpretation/labelling, case study and
  essay. Questions are versioned and de-duplicated by fingerprint.
- **Moderation engine** — validates relevance, coverage, clarity, answer keys,
  mark allocation, difficulty, duplicates, distractor quality, visual
  consistency and rubric completeness. Statuses: `approved`,
  `requires_review`, `rejected`. Examinations with critical errors are not
  published.
- **Examination website** — responsive, keyboard accessible, with countdown
  timer, question and section navigation, question status, flag-for-review,
  autosave, submission confirmation and a results interface.
- **Practice and formal modes** — practice offers immediate feedback and
  explanations; formal mode withholds answers and memoranda until authorised
  release.
- **Marking** — deterministic marking for objective questions against verified
  answer keys; rubric-based marking with rationale for extended responses, plus
  a human-review workflow.
- **Performance intelligence** — results by topic, learning outcome,
  difficulty and Bloom level, repeated mistakes, knowledge gaps, mastery
  classification and targeted revision recommendations.
- **PDF deliverables** — a memorandum/marking guide and a subject mastery and
  examination preparation guide, both bound to the same examination version.
- **CLI** — the full workflow without a browser.

## Getting started

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

export EXAMGEN_SECRET_KEY="a-long-random-secret"
export EXAMGEN_DATA_DIR="$PWD/data"

examgen init-db
examgen serve --host 0.0.0.0 --port 8000
```

Open <http://localhost:8000>, register a student account, create a subject
workspace, and upload that subject's coursework.

See [Deployment](#deployment) for the full environment variable reference.

## Command line

```bash
examgen init-db
examgen user-create --email student@example.com --password "..." --name "Student"
examgen subject-create --owner student@example.com --name "Data Structures" --code CS201
examgen ingest CS201 ./notes/lecture-notes.pdf ./papers/past-paper-2023.pdf
examgen topics CS201
examgen visuals-propose CS201 && examgen visuals-decide CS201 approve
examgen generate CS201 --title "Midterm" --questions 12 --marks 100 --duration 120
examgen questions <examination-id> --answers
examgen deliverables <examination-id>
examgen analytics CS201
```

## HTTP API

Authentication is a bearer JWT from `POST /api/auth/register` or
`POST /api/auth/login`. Key routes:

- `POST/GET /api/workspaces` — subject workspaces
- `POST /api/workspaces/{id}/documents`, `POST .../classify`,
  `GET .../sufficiency`, `GET .../topics`
- `POST .../visuals/propose`, `GET .../visuals`,
  `POST .../visuals/{visual_id}/decision`
- `POST/GET .../blueprints`, `POST .../blueprints/{id}/generate`
- `GET .../examinations`, `POST .../examinations/{id}/moderate`,
  `POST .../examinations/{id}/publish`
- `POST .../examinations/{id}/attempts`, `PUT /api/attempts/{id}/responses`,
  `POST /api/attempts/{id}/submit`, `GET /api/attempts/{id}/result`
- `GET .../analytics`, `POST .../examinations/{id}/deliverables`,
  `GET .../examinations/{id}/deliverables/{kind}/download`

Interactive docs are served at `/docs`.

## Architecture

```
examgen/
  api/          FastAPI application and routers (auth, workspaces, exams)
  services/     Domain logic: extraction, classification, generation,
                visuals, examination, moderation, marking, analytics, pdf
  models.py     SQLAlchemy entity model
  schemas.py    Pydantic request/response contracts
  security.py   Password hashing, JWT auth, workspace authorisation
  cli.py        Command line interface
  static/       Vanilla JS/HTML frontend (portal + examination website)
  templates/    Jinja templates
tests/          Milestone acceptance tests (M1–M8) plus CLI coverage
```

Student-facing question payloads never include answer keys; authoring views are
separate schemas. Memoranda are withheld in formal mode until released.

## Deployment

The application is a single FastAPI process with no external services, so it
runs anywhere Python 3.10+ or Docker is available. All state lives under
`EXAMGEN_DATA_DIR`, so **mount a persistent volume there** or the database,
uploads and PDFs are lost on redeploy.

`EXAMGEN_SECRET_KEY` is required in production. Without it each process mints a
random key and every issued token is invalidated on restart.

### Docker

```bash
docker build -t examgen .
docker run -d --name examgen -p 8000:8000 \
  -e EXAMGEN_SECRET_KEY="$(openssl rand -hex 32)" \
  -v examgen-data:/data \
  examgen
```

Or with Compose (see `docker-compose.yml`):

```bash
docker compose up --build
```

### Platform as a service

`app.py` exposes a module-level `app`, and `Procfile` provides the web command,
so Render, Railway, Heroku and Fly.io can deploy the repository directly.

- Build: `pip install .`
- Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`
- Required env: `EXAMGEN_SECRET_KEY`
- Recommended env: `EXAMGEN_DATA_DIR` pointing at a mounted disk

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `EXAMGEN_SECRET_KEY` | JWT signing key. **Required in production.** | random per process |
| `EXAMGEN_DATA_DIR` | Database, uploads, assets, generated PDFs | `./data` |
| `EXAMGEN_DATABASE_URL` | SQLAlchemy URL (e.g. Postgres) | SQLite in the data dir |
| `EXAMGEN_MAX_UPLOAD_MB` | Per-file upload limit | 50 |
| `EXAMGEN_TOKEN_TTL_MINUTES` | Access token lifetime | 720 |
| `EXAMGEN_LLM_API_KEY` | Optional model access for supplementary knowledge | unset |
| `EXAMGEN_ALLOW_SUPPLEMENTARY` | Permit external knowledge, clearly labelled | false |

Without an LLM key the deterministic offline engine drives the whole workflow,
so the platform is fully functional with no external API.

### Scale-out note

SQLite with a single process is the default and suits a single instance. To run
multiple workers or replicas, point `EXAMGEN_DATABASE_URL` at Postgres **and**
give every replica the same `EXAMGEN_DATA_DIR` on shared storage — uploads and
generated PDFs are written to the filesystem, not the database.

## Tests

```bash
python -m pytest -q
```

The suite covers milestones 1–8: resource management and isolation, visual
assessment, question bank and generation, moderation and publication, the
examination website, practice/formal execution, marking and analytics, PDF
deliverables, and the CLI.
