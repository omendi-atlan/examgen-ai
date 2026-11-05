# EXAMGEN AI

AI-assisted examination generation and personalised revision platform.

## Current release: 0.2.0 foundation

This repository contains the first deployable application foundation: a responsive Next.js student workspace, configurable practice/simulation assessments, a server-side AI generation endpoint, objective scoring, Docker deployment files, and CI checks.

### Stack
- Next.js App Router, React and TypeScript
- OpenAI API (server-side only)
- Zod request/response validation
- Docker / Docker Compose
- GitHub Actions

### Run locally
```bash
cp .env.example .env.local
# Set OPENAI_API_KEY in .env.local
npm install
npm run dev
```
Open http://localhost:3000.

### Run with Docker
```bash
cp .env.example .env
# Set OPENAI_API_KEY in .env
docker compose up --build
```

### Security
Never commit `.env.local`, `.env`, credentials, or API keys. Configure secrets in the deployment environment. If an API key has been exposed, revoke it and issue a replacement.

### Scope and accuracy
The sample assessment is demonstration content, not a verified curriculum paper. The current generation endpoint creates validated question sets. Objective items can be scored locally; written responses still require a rubric-based marking service. Authentication, persistent question-bank workflows, source-document ingestion, visual approval, adaptive revision scheduling and PDF exports are planned modules, not claimed as completed functionality.

## Examination Intelligence Plugin (EIP)

A standalone, independently versioned plugin specification and implementation plan has been approved and is being developed on an isolated feature branch.

- [EIP module specification](plugins/examination-intelligence/README.md)
- [EIP implementation skill plan](plugins/examination-intelligence/SKILL.md)
- [EIP acceptance test plan](docs/EXAMINATION_INTELLIGENCE_ACCEPTANCE_TESTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)

The EIP specification is not a claim that the module has been implemented or qualified. The acceptance matrix is established; runtime execution is pending implementation. Existing student workflows and current platform capabilities remain the compatibility baseline.
