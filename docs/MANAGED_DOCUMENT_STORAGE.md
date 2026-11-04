# Managed academic document storage

## Storage contract

- PostgreSQL remains the source of truth for document identity, immutable versions, SHA-256 fingerprints, provenance and opaque storage keys.
- `DOCUMENT_STORAGE_BACKEND=local` preserves the existing private-volume implementation.
- `DOCUMENT_STORAGE_BACKEND=s3` selects an S3-compatible private bucket for uploads and worker reads.
- API and worker processes must use the same backend, bucket, region, endpoint and credentials/workload identity.
- For Cloudflare R2, set `OBJECT_STORAGE_REGION=auto` and `OBJECT_STORAGE_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com`. R2 uses the S3-compatible API and the region value `auto`.
- S3 objects are uploaded with server-side AES-256 encryption. No public ACL is applied. Keep the bucket private and require TLS for object API access.
- The browser never receives object-store credentials or object URLs. Downloads are performed by the server-side worker.
- Worker reads verify the stored object's byte length and SHA-256 against the immutable `document_versions` row before extraction.

## Cloudflare R2 setup

1. In the Cloudflare dashboard, open **Storage & databases → R2 → Overview**. Enable R2 if this is the first use.
2. Create a dedicated private bucket, for example `examgen-academic-resources`. Do not enable public bucket access.
3. Under **Manage R2 API Tokens**, create an R2 token with **Object Read & Write** permission and scope it to this bucket only. The application needs object read, write, head and list capabilities; it does not need bucket administration.
4. Copy the Access Key ID and Secret Access Key once and store them in your deployment secret manager. Do not commit them, paste them into chat, or expose them through `NEXT_PUBLIC_*` variables.
5. Copy the account ID from Cloudflare. The standard S3 endpoint is `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`. If you deliberately create a jurisdiction-restricted bucket, use its matching jurisdiction endpoint instead.
6. Configure the API and every document worker with the same values:

   ```dotenv
   DOCUMENT_STORAGE_BACKEND=s3
   OBJECT_STORAGE_BUCKET=examgen-academic-resources
   OBJECT_STORAGE_REGION=auto
   OBJECT_STORAGE_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
   OBJECT_STORAGE_ACCESS_KEY=<R2_ACCESS_KEY_ID>
   OBJECT_STORAGE_SECRET_KEY=<R2_SECRET_ACCESS_KEY>
   ```

7. Keep `DOCUMENT_STORAGE_PATH` mounted to the existing private local document volume during migration. Do not delete local files or change database storage keys during the first cutover.
8. Restart API and worker processes after injecting secrets, then run the provider smoke test below against the intended staging bucket.

The S3 adapter now requires an explicit HTTPS endpoint whenever S3 mode is enabled. This prevents a missing endpoint from silently sending requests to the default AWS endpoint.

## Local-to-managed migration

1. Back up PostgreSQL and the private document volume.
2. Provision a private S3-compatible bucket with public access blocked, TLS-only access, encryption at rest and least-privilege API/worker permissions.
3. Configure the S3 backend, bucket, region, endpoint and server-side credentials for both API and worker.
4. Keep `DOCUMENT_STORAGE_PATH` pointed at the existing local volume. Do not remove or replace that volume.
5. Run `python backend/scripts/migrate_document_storage.py` from the backend package environment. The utility checks every local file against the database SHA-256 and byte count, uploads using the existing storage key, then downloads and verifies the managed copy.
6. Re-run the migration after an interrupted run. Uploading to the same immutable object key is idempotent; database rows and keys are not rewritten.
7. Deploy API and worker with the S3 backend and run ingestion plus extraction smoke tests. Keep local copies and backups during the observation window.
8. Only after a verified backup, successful worker reads and an approved rollback window may operators retire the old local volume. The migration utility's optional `--delete-local` flag is deliberately explicit and should not be used during initial cutover.

## Provider smoke test

After provisioning the private bucket and configuring the API/worker environment, run the real provider check from the backend environment:

```bash
python backend/scripts/verify_object_storage.py
```

The check uploads a short-lived random-key object through the production adapter, downloads it, verifies byte-for-byte content plus expected size and SHA-256, and deletes it in a `finally` block. Run it against the intended staging bucket before migration. It does not create or alter PostgreSQL document records.

## Rollback

Set `DOCUMENT_STORAGE_BACKEND=local` for both API and worker and restore the original private volume. Since the migration preserves all database storage keys and retains local files by default, rollback does not require a database migration or document-version rewrite.

## Operational controls

- Use workload identity where available; otherwise inject credentials through a secret manager, never source control.
- Restrict bucket permissions to the required bucket and operations.
- Enable bucket versioning and provider-side access logging according to the deployment's retention policy.
- Alert on object upload, head, download, integrity and delete failures.
- Do not make the bucket public or generate browser-facing presigned URLs for source materials.
