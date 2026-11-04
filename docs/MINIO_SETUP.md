# MinIO setup for EXAMGEN AI

This guide configures a persistent local MinIO S3-compatible service for development and integration testing. It does not turn a single-node, single-drive MinIO instance into a highly available production object store.

## 1. Prerequisites

- Docker Engine and the Docker Compose plugin
- The repository checked out locally
- A Python backend environment for running the storage verification utility

## 2. Create local secrets

Copy the sample environment file and generate a long random MinIO root password. Keep the resulting `.env` file private and out of source control.

```bash
cp .env.example .env
openssl rand -hex 32
``

Set these values in `.env` (use the generated random value for the password):

```dotenv
MINIO_ROOT_USER=examgen-local-minio
MINIO_ROOT_PASSWORD=<your-generated-random-secret>
DOCUMENT_STORAGE_BACKEND=s3
OBJECT_STORAGE_BUCKET=examgen-academic
OBJECT_STORAGE_REGION=us-east-1
OBJECT_STORAGE_ENDPOINT_URL=http://minio:9000
OBJECT_STORAGE_ACCESS_KEY=examgen-local-minio
OBJECT_STORAGE_SECRET_KEY=<same-generated-random-secret>
OBJECT_STORAGE_SERVER_SIDE_ENCRYPTION=
```

The empty encryption setting is only for this local MinIO profile without a KMS. The adapter omits the SSE request header in that mode. Protect the Docker data volume and host disk with full-disk encryption. Never use this no-KMS setting for production: production configuration rejects it when S3 storage is selected.

## 3. Start MinIO and the application stack

```bash
docker compose --profile minio up -d --build
```

The MinIO API is available to containers at `http://minio:9000`; the local host ports are bound to `127.0.0.1` only. The console is at [http://127.0.0.1:9001](http://127.0.0.1:9001). Sign in with the root credentials from `.env`.

The API and document worker must use identical S3 endpoint, bucket, region and credentials. The supplied Compose configuration passes the same object-storage settings to both services.

## 4. Create the private bucket and enable versioning

Use the MinIO Client (`mc`) from a machine with access to the local API. After installing `mc`, run:

```bash
mc alias set examgen http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mb --ignore-existing examgen/examgen-academic
mc version enable examgen/examgen-academic
mc ls examgen
```

If your shell does not export values from `.env`, enter the same values from that file for the alias command. Keep the bucket private; do not enable anonymous/public access.

## 5. Verify the real storage adapter

After the API container is running, execute the repository's provider smoke test inside the backend environment:

```bash
docker compose exec -e PYTHONPATH=/srv/examgen/backend api \\
  python /srv/examgen/backend/scripts/verify_object_storage.py
```

The test creates a random temporary object, uploads it through the actual application adapter, reads it back, checks byte-for-byte content, size and SHA-256, then attempts cleanup. A successful result is the first real provider-level verification; Compose starting successfully is not enough.

Then upload a representative PDF through the application and confirm that the document worker can read and extract it. Check the API and worker logs for storage, checksum, scanner and extraction errors.

## 6. Useful diagnostics

```bash
docker compose --profile minio ps
docker compose logs --tail=100 minio api document-worker
docker compose exec minio mc ready local
```

To stop the stack without deleting stored data:

```bash
docker compose --profile minio down
```

The named `examgen-minio-data` volume persists across container recreation. Do not use `docker compose down -v` unless you intentionally want to delete local database, document and MinIO data.

## 7. Production requirements

Before using MinIO for real student records, replace the single-node development deployment with a supported production topology, persistent redundant storage, TLS, network isolation, backups and tested restore procedures. Create a dedicated least-privilege service identity for EXAMGEN AI rather than using the MinIO root identity. Configure and test a supported KMS for SSE-S3/SSE-KMS, or document an approved equivalent encryption-at-rest design. The current application adapter supports S3 SSE values `AES256` and `aws:kms`; the selected KMS and bucket policy must be validated against the deployed MinIO edition and version. Do not expose the MinIO console or S3 API directly to the public internet.

For migration from existing local document storage, follow [Managed academic document storage](MANAGED_DOCUMENT_STORAGE.md). Back up PostgreSQL and the local document volume first; run the migration utility; verify every object; test worker reads; and retain the local copy through the rollback window. Do not use `--delete-local` during initial cutover.

## References

- [MinIO Docker quickstart](https://github.com/minio/minio/blob/master/docs/docker/README.md)
- [MinIO server-side encryption overview](https://github.com/minio/minio/blob/master/docs/security/README.md)
- [EXAMGEN AI managed storage operations](MANAGED_DOCUMENT_STORAGE.md)
