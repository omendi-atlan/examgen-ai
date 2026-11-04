# Ingestion security and qualification controls

## Authentication abuse protection

The API applies database-backed fixed-window limits to public identity endpoints:

- Login: 10 attempts per client address per 15-minute window.
- Registration: 5 attempts per client address per 60-minute window.
- Exceeded requests return HTTP 429 and a `Retry-After` header.
- Counters are updated with atomic PostgreSQL/SQLite upserts, so multiple API processes share the same limit.
- Counter keys are SHA-256 digests of scope, client address and subject; raw addresses are not stored in the rate-limit table.
- Expired buckets older than 24 hours are pruned during authentication requests.

The application uses the transport peer address (`request.client.host`) and intentionally does not trust arbitrary `X-Forwarded-For` values. In a reverse-proxy deployment, configure the ASGI server to trust forwarded headers only from explicitly trusted proxy addresses, and ensure direct access to the API container is blocked.

These limits protect the public authentication endpoints. Production deployments should additionally enforce edge-level request and connection limits for all routes, including uploads, and configure request-body limits and timeouts at the ingress/load balancer.

## Tenant and role qualification

The test suite verifies that:

- Unauthenticated requests cannot access workspace APIs.
- A user without active workspace membership receives a non-disclosing 404.
- A student membership cannot access examiner-only academic ingestion endpoints.
- A document cannot be accessed across workspace boundaries.
- A taxonomy topic from another workspace cannot be assigned to a document.
- Extraction review history is workspace-isolated and decisions are append-only.
- A route-wide SQLite API matrix exercises all academic upload, version, document, segment, taxonomy, classification and extraction-review endpoints: non-editor members receive 403, while non-members receive a non-disclosing 404 for cross-workspace requests.
- A dedicated PostgreSQL integration test verifies route-level 403 role enforcement and 404 cross-tenant isolation for document, taxonomy, segment, classification and extraction-review access.

## Provenance and citation qualification

Every extracted segment must retain its original source locator and metadata. Academic acceptance tests assert stable segment ordering, locator presence and traceability to the immutable source version. OCR pages retain page numbers and extraction-method provenance. A source version is not automatically accepted; a human examiner decision is required before downstream academic workflows may rely on it.

## Processing and concurrency qualification

CI runs PostgreSQL 16 migrations and concurrency tests. Worker qualification covers distinct concurrent job claims, expired-lease recovery, fencing-token ownership and atomic shared authentication rate limits. Extraction limits are enforced before output is persisted. Synthetic qualification covers a multi-megabyte PDF container, concurrent 256 KB text extraction and a three-page OCR fallback harness that verifies page locators and OCR provenance. The OCR harness isolates PDFium/Tesseract integration contracts; it is not a substitute for benchmarking a real scanned corpus or multiple worker replicas.

## Release caveats

- CI tests are not a substitute for a production traffic test with realistic PDFs, OCR-heavy scans and multiple API/worker replicas.
- Configure real provider-managed object storage and verify its IAM/bucket policy before switching production.
- Run the local-to-managed migration against a backup and staging dataset before any production cutover.
- Production ingress must enforce TLS, body-size limits, connection timeouts, trusted proxy configuration and edge rate limits.
