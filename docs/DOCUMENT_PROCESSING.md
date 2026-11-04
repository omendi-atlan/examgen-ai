# Academic document processing

## Processing lifecycle

1. An authenticated examiner uploads a source file. The original is stored under a generated private key and its immutable version/provenance is committed.
2. The API creates a durable, version-scoped processing job in the same database transaction. The upload response reports a queued extraction; it does not wait for OCR or parsing.
3. A separate worker claims queued jobs using row-level locking on PostgreSQL, processes the immutable source, and persists page/slide/paragraph-addressable segments.
4. Extraction quality heuristics report sparse, empty, failed, and OCR-required content. These are review signals, not academic correctness claims.
5. A human examiner reviews source segments and confirms subject/topic classification. Extraction quality never silently approves a source or classification.

## Operational requirements

- Run the worker with `python -m app.worker` in a separate process/container.
- API and worker must share the same PostgreSQL database and private document volume.
- Worker concurrency relies on PostgreSQL `FOR UPDATE SKIP LOCKED`; SQLite is for unit tests, not multi-worker production.
- Failed jobs retry up to the configured job limit; terminal failures retain a bounded error category.
- OCR uses Tesseract and PDFium. The worker image installs the Tesseract executable; OCR is applied to pages without selectable text.
- Set `TESSERACT_CMD` only when the binary is not on PATH. Do not enable untrusted PDF JavaScript or embedded actions.
- Keep source originals immutable. Reprocessing creates a new processing job and extraction record only through an explicit administrative operation in a future release.

## Examiner review interface

- Open the Next.js route at `/documents`.
- Sign in with an existing examiner/moderator workspace account, provide the workspace UUID, and load its source documents.
- Select a document and immutable version to inspect extraction status, quality signals, topic assignments and source-addressable text segments.
- The interface keeps the access token in page memory only; it does not persist credentials in browser storage.
- Configure `CORS_ALLOWED_ORIGINS` for the deployed frontend origin before using the separate API host.

## Quality review

The persisted quality report contains character count, page count, segment count, outcome and reasons. Low text density is a heuristic that flags a document for human review; it must not be treated as proof of missing content. OCR output retains page locators and is labelled as OCR-derived metadata. Academic content remains untrusted data, never executable instructions.
