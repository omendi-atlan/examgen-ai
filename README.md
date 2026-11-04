# EXAMGEN AI

AI-assisted examination generation and personalised revision platform.

## Current release: 0.2.0 foundation

The current deployable foundation includes a responsive Next.js student workspace, configurable practice/simulation assessments, a TypeScript Worker AI generation endpoint, objective question validation, Docker deployment files and CI checks.

## Approved target architecture

The approved target is an integrated academic examination intelligence platform. Generated student examinations will be responsive websites built with HTML, CSS and JavaScript. Python will be the authoritative backend, with FastAPI, Pydantic, SQLAlchemy and PostgreSQL as the recommended foundation.

The existing Next.js workspace may remain as the authoring/admin shell during a staged migration. The TypeScript Worker is transitional and will be retired only after Python API parity and verified cutover. No current functionality should be removed before migration tests pass.

## Current stack (0.2.0)

- Next.js App Router, React and TypeScript
- TypeScript Cloudflare Worker
- OpenAI API (server-side only)
- Zod request/response validation
- Docker / Docker Compose
- GitHub Actions

## Planned capabilities

Academic document ingestion, subject/topic classification, visual generation and approval, examination blueprints, reusable question bank, answer/rubric generation, examination moderation, HTML/CSS/JS exam publishing, persistent attempts, server-side marking, analytics, personalised revision and PDF exports are target capabilities, not completed features.

## Run current foundation locally

```bash
cp .env.example .env.local
# Set OPENAI_API_KEY in .env.local
npm install
npm run dev
```

Open http://localhost:3000.

## Security

Never commit `.env.local`, `.env`, credentials, API keys, student records or private academic resources. Configure secrets in deployment secret management. If a key has been exposed, revoke it and issue a replacement.

## Documentation

- [Approved integrated skill and architecture plan](docs/EXAMGEN_AI_SKILL_PLAN.md)
- [Architecture summary](docs/ARCHITECTURE.md)
- [Delivery roadmap](docs/ROADMAP.md)
- [Domain modules](modules/README.md)
