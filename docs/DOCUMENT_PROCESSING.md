# Academic document processing

## Processing lifecycle

1. An authenticated examiner uploads a source file. The original is streamed to a temporary private file, hashed, format-validated and malware-scanned before it is moved to its immutable generated storage key.
2. The API creates a durable, version-scoped processing job in the same database transaction. The upload response reports a queued extraction; it does not wait for OCR or parsing.
3. A separate worker claims queued jobs using PostgreSQL row-level locking with `FOR UPDATE SKIP LOCKED`, a unique lease token and an expiry timestamp.
4. The worker extracts outside a database transaction, then locks the job and verifies its lease token before committing results. A stale worker cannot overwrite a newer worker's result.
5. Expired leases are recovered on subsequent queue polls. Jobs are requeued while attempts remain; exhausted jobs become terminal failures. Attempt counts increment at claim time, so a process crash consumes an attempt.
6. Extraction quality heuristics report sparse, empty, failed, and OCR-required content. These are review signals, not academic correctness claims.
7. A human examiner reviews source segments and confirms subject/topic classification. Extraction quality never silently approves a source or classification.

## Malware scanning

- Docker Compose runs a private ClamAV daemon; it is not exposed as a host port.
- The API scans upload bytes using ClamAV's INSTREAM protocol before accepting a file into permanent storage.
- A malware detection rejects the upload. If the scanner is unavailable or returns an indeterminate result, the upload is rejected rather than accepted unscanned.
- Production configuration requires `MALWARE_SCAN_ENABLED=true`. Local development can leave scanning disabled when not running ClamAV; this is not a production setting.
- ClamAV signature definitions are persisted in the `examgen-clamav-data` volume and updated by the ClamAV container.

## Resource and archive limits

- Upload size is bounded by `MAX_DOCUMENT_UPLOAD_BYTES` (default 20 MB; maximum 100 MiB).
- Office archives are checked for entry count, total uncompressed size (80 MiB ceiling), compression ratio, encryption, required package parts and symbolic links.
- PDF page count is bounded by `MAX_PDF_PAGES` (default 100).
- OCR rendering is bounded by `MAX_PDF_PAGE_PIXELS` (default 20 million pixels per page); Tesseract is terminated after `OCR_PAGE_TIMEOUT_SECONDS` (default 15 seconds) per page.
- PPTX slide count is capped at 500. All formats enforce `MAX_EXTRACTED_CHARACTERS` (default 10 million characters).
- The default 20 MB upload limit stays below ClamAV's typical 25 MB stream ceiling. If raising the upload limit, increase ClamAV StreamMaxLength, MaxFileSize and MaxScanSize consistently and verify a scan larger than the new limit. Resource limits should be tuned against representative course packs and available worker memory. Do not raise limits without OCR and archive-bomb testing.

## Operational requirements

- Run the worker with `python -m app.worker` in a separate process/container.
- API and worker must share the same PostgreSQL database and private document volume.
- Worker concurrency relies on PostgreSQL `FOR UPDATE SKIP LOCKED`; SQLite is for unit tests, not multi-worker production.
- Configure `DOCUMENT_JOB_LEASE_SECONDS` for the expected bounded processing time. The default is one hour; a dedicated heartbeat session renews active leases during long-running extraction, and expired leases are recovered by the next worker poll.
- The worker loop logs and backs off on transient database errors; the container restart policy covers process termination.
- OCR uses Tesseract and PDFium. The worker image installs the Tesseract executable; OCR is applied to pages without selectable text.
- Keep Tesseract available on the worker PATH. Do not enable untrusted PDF JavaScript or embedded actions.
- Keep source originals immutable. Reprocessing creates a new processing job and extraction record only through an explicit administrative operation in a future release.

## Examiner review interface

- Open the Next.js route at `/documents`.
- Sign in with an existing examiner/moderator workspace account, provide the workspace UUID, and load its source documents.
- Select a document and immutable version to inspect extraction status, quality signals, topic assignments and source-addressable text segments.
- The interface keeps the access token in page memory only; it does not persist credentials in browser storage.
- Configure `CORS_ALLOWED_ORIGINS` for the deployed frontend origin before using the separate API host.

## Validation

- CI runs Alembic migrations against PostgreSQL 16 before executing the test suite.
- PostgreSQL integration tests use a dedicated ephemeral CI database to verify concurrent worker claims, expired-lease recovery and terminal retry exhaustion.
- Unit tests cover clean, infected and unavailable scanner outcomes, plus PDF page-count and extraction-size limits.
- Never use a shared or production database for the integration test suite: its fixture creates and drops the application schema.

## Quality review

The persisted quality report contains character count, page count, segment count, outcome and reasons. Low text density is a heuristic that flags a document for human review; it must not be treated as proof of missing content. OCR output retains page locators and is labelled as OCR-derived metadata. Academic content remains untrusted data, never executable instructions.
