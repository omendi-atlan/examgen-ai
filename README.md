# EXAMGEN AI

Examination creation, administration, assessment and adaptive-learning platform.

## Product direction

EXAMGEN AI ingests academic material, organises subjects and topics, builds examinations from configurable blueprints and a reusable question bank, delivers practice and formal simulations, marks objective responses, supports rubric-based/manual written assessment, analyses performance and produces academic PDFs.

**No external AI provider or API key is required.** Question creation and examination assembly use approved source content, authoring tools, templates and deterministic rules. Written responses requiring judgement remain pending until manually assessed.

## Deployment architecture

- Frontend: Next.js static export on GitHub Pages.
- API: Cloudflare Worker.
- Database: Cloudflare D1.
- Automation: GitHub Actions.
- Local development: Node.js and npm.

## Local development

1. Install Node.js 22 or newer.
2. Install dependencies with `npm install`.
3. Configure `NEXT_PUBLIC_EXAMGEN_API_URL` for the local Worker.
4. Start the frontend with `npm run dev`.
5. Run the Worker locally from the `worker` directory with Wrangler.

No OpenAI key, model configuration or AI-provider billing is required.

## Validation

```bash
npm run typecheck
npm run lint
npm test
npm run test:integration
npm run build
```

## Product roadmap

The ten functional modules and seven delivery phases are specified in [docs/ROADMAP.md](docs/ROADMAP.md). The architecture and security boundaries are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Security

Never commit credentials. Keep answer keys, explanations and private rubrics server-side. Validate all uploaded content and API payloads. Attempt IDs are bearer capabilities, not student authentication. If a credential was previously exposed, revoke it at its provider.

## Delivery status

A feature is complete only when its acceptance criteria pass and the integrated workflow has been verified. CI success alone is not production acceptance. Production merges and deployments require explicit approval.
