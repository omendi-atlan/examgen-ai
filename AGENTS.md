# AGENTS.md

Repository knowledge for agents working on EXAMGEN AI.

## What this is

Academic examination platform: FastAPI backend + vanilla JS/HTML frontend +
reportlab PDFs + argparse CLI. One isolated workspace per subject/module.
Milestones M1–M8 are implemented and covered by tests.

## Layout

- `examgen/api/` — FastAPI app and routers (`auth`, `workspaces`, `exams`,
  `assistant`)
- `examgen/services/` — domain logic; the place most changes belong
  - `extraction.py` — file → `ExtractedContent` chunks
  - `classification.py` — topics, subtopics, outcomes, sufficiency, duplicates
  - `textutil.py` — tokenising, Bloom mapping, diagram-type detection
  - `visuals.py` — visual requirement assessment + SVG construction
  - `generation.py` — question generation and fingerprints
  - `examination.py` — blueprint → examination, snapshots, deliverables
  - `assistant.py` — grounded subject chatbot (retrieval + intent composers)
  - `moderation.py`, `marking.py`, `analytics.py`, `pdf.py`, `workspace.py`
- `examgen/static/js/` — `portal.js` (subject portal), `exam.js` (exam website),
  `chat.js` (subject assistant panel)
- `tests/` — milestone acceptance tests + `test_cli.py`

## Commands

```bash
python -m pytest -q                       # full suite (42 tests)
python -m compileall -q examgen tests     # syntax check
examgen --help                            # CLI surface

# run the site
EXAMGEN_DATA_DIR=$PWD/data EXAMGEN_SECRET_KEY=dev-secret-key-for-local-demo-only-not-prod \
  python -m uvicorn examgen.api.app:create_app --factory --host 0.0.0.0 --port 12000
```

## Conventions and gotchas

- **Test isolation**: `tests/conftest.py` sets `EXAMGEN_DATA_DIR` /
  `EXAMGEN_DATABASE_URL` to a temp dir and calls `reset_settings()` +
  `reset_engine()` before `init_db()`. Reuse that pattern for new fixtures;
  never let a test touch the developer's `data/`.
- **Workspace isolation is a hard requirement.** Every query that reads
  academic content must be scoped by `workspace_id`. Cross-subject leakage is
  the single most serious defect class here.
- **Never expose answer keys to students.** `schemas.py` has separate
  student-facing and authoring shapes; the exam website only receives the
  former. Memoranda stay withheld in formal mode until `release-feedback`.
- **Provenance matters.** Generated questions and notes must cite the source
  document/chunk. Do not attribute AI-generated text to an uploaded document.
- **No fabricated content.** When coursework is thin, report the gap via the
  sufficiency report instead of inventing material.
- `store_upload(db, workspace, filename, content, content_type="",
  declared_kind=None)` — an explicit `declared_kind` wins over filename
  inference. The CLI passes it through `--kind`.
- `portal.js` deep links: `?workspace=<id>&view=<tab>` where tab is one of
  `resources`, `classification`, `visuals`, `examinations`, `results`.
  `selectTab()` keeps the URL in sync via `history.replaceState`.
- Templates load static assets with `?v={{ app_version }}` for cache busting —
  bump `__version__` in `examgen/__init__.py` if a stale asset causes confusion.
- `textutil.keyword_hits` uses word boundaries for single words so short
  keywords don't match inside longer ones. Keep that when adding diagram
  keywords.
- **The subject assistant (`services/assistant.py`) is grounded, not generative.**
  `retrieve()` selects passages from the workspace's own chunks; the composers
  only arrange them. Never let an assistant reply assert something that is not
  either a retrieved excerpt or a value read from a persisted record. The
  `_INTENTS` list is order-sensitive — the first match wins, so keep specific
  navigational intents above the catch-all `explain`. Chat sessions are scoped
  by `workspace_id` **and** `user_id`; keep both checks when adding routes.
- Topic discovery folds n-gram fragments into full phrases (a bigram is dropped
  when a containing trigram is at least as frequent). Expect phrase-style topic
  names, not single words.

## Git

Single `master` branch, currently one commit. Commit with a descriptive
message; co-author line is `Co-authored-by: openhands <openhands@all-hands.dev>`.
