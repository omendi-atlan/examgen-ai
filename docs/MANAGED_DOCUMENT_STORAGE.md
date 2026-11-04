# Managed academic document storage

## Storage contract

- PostgreSQL remains the source of truth for document identity, immutable versions, SHA-256 fingerprints, provenance and opaque storage keys.
- `DOCUMENT_STORAGE_BACKEND=local` preserves the existing private-volume implementation.
- `DOCUMENT_STORAGE_BACKEND=s3` selects an S3-compatible private bucket for uploads and worker reads.
- API and worker processes must use the same backend, bucket, region, endpoint and credentials/workload identity.
- S3 objects are uploaded with server-side AES-256 encryption. No public ACL is applied. Keep bucket public-access blocks enabled and require TLS in the bucket policy.
- The browser never receives object-store credentials or object URLs. Downloads are performed by the server-side worker.
- Worker reads verify the stored object's byte length and SHA-256 against the immutable `document_versions` row before extraction.

## Local MinIO development profile

For a persistent local S3-compatible target, see [MinIO development setup](MINIO_SETUP.md). The Compose profile is opt-in and binds the S3 API and console to loopback only. It is for development and integration testing, not a highly available production deployment.

## Local-to-managed migration

1. Back up PostgreSQL and the private document volume.
2. Provision a private S3-compatible bucket with public access blocked, TLS-only access, encryption at rest and least-privilege API/worker permissions.
3. Configure `DOCUMENT_STORAGE_BACKEND=s3`, `OBJECT_STORAGE_BUCKET`, `OBJECT_STORAGE_REGION`, and either workload identity or the server-side access/secret pair. Configure the same values for API and worker.
4. Keep `DOCUMENT_STORAGE_PATH` pointed at the existing local volume. Do not remove or replace that volume.
5. Run `python backend/scripts/migrate_document_storage.py` from the backend package environment. The utility checks every local file against the database SHA-256 and byte count, uploads using the existing storage key, then downloads and verifies the managed copy.
6. Re-run the migration after an interrupted run. Uploading to the same immutable object key is idempotent; database rows and keys are not rewritten.
7. Deploy API and worker with the S3 backend and run ingestion plus extraction smoke tests. Keep local copies and backups during the observation window.
8. Only after a verified backup, successful worker reads and an approved rollback window may operators retire the old local volume. The migration utility's optional `--delete-local` flag is deliberately explicit and should not be used during initial cutover.

## Provider smoke test

After provisioning the private bucket and configuring the API/worker environment, run the real provider check from the backend environment:

\`\`\`bash
python backend/scripts/verify_object_storage.py
\`\`\`

The check uploads a short-lived random-key object through the production adapter, downloads it, verifies byte-for-byte content plus expected size and SHA-256, and deletes it in a `finally` block. Run it against the intended staging bucket before migration. It does not create or alter PostgreSQL document records.

## Rollback

Set `DOCUMENT_STORAGE_BACKEND=local` for both API and worker and restore the original private volume. Since the migration preserves all database storage keys and retains local files by default, rollback does not require a database migration or document-version rewrite.

## Operational controls

- Use workload identity where available; otherwise inject credentials through a secret manager, never source control.
- Restrict bucket permissions to the required bucket/prefix and operations.
- Enable bucket versioning and provider-side access logging according to the deployment's retention policy.
- Alert on object upload, head, download, integrity and delete failures.
- Do not make the bucket public or generate browser-facing presigned URLs for source materials.
