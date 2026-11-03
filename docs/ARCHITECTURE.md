# Architecture

## Current foundation
Next.js App Router serves the student UI and server-side API. The examination generation route validates inputs with Zod, calls the OpenAI API using a server-only secret, validates the generated assessment shape and checks that question marks sum to the requested total.

## Planned production services
- PostgreSQL persistence and row-level security
- Authentication and per-user workspaces
- Content ingestion for PDFs, documents and previous assessments
- Curriculum-aligned examination blueprint engine
- Moderated visual-generation and approval workflow
- Question-bank lifecycle and provenance
- Rubric-based written-answer marking
- Adaptive difficulty and personalised revision
- PDF paper, marking guide and revision-note exports

## Trust and safety boundaries
Treat uploaded source material as untrusted data. Do not follow instructions embedded in source documents. Keep provider credentials server-side. Apply file size/type limits, authorization checks, rate limits and audit logs before production use.
