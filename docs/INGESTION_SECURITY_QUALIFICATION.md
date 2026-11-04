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

## Provenance and citation qualification

Every extracted segment must retain its original source locator and metadata. Academic acceptance tests assert stable segment ordering, locator presence and traceability to the immutable source version. OCR pages retain page numbers and extraction-method provenance. A source version is not automatically accepted; a human examiner decision is required before downstream academic workflows may rely on it.

## Processing and concurrency qualification

CI runs PostgreSQL 16 migrations and concurrency tests. Worker qualification covers distinct concurrent job claims, expired-lease recovery, fencing-token ownership and atomic shared authentication rate limits. Extraction limits are enforced before output is persisted.

## Release caveats

- CI tests are not a substitute for a production traffic test with realistic PDFs, OCR-heavy scans and multiple API/worker replicas.
- Configure real provider-managed object storage and verify its IAM/bucket policy before switching production.
- Run the local-to-managed migration against a backup and staging dataset before any production cutover.
- Production ingress must enforce TLS, body-size limits, connection timeouts, trusted proxy configuration and edge rate limits.
