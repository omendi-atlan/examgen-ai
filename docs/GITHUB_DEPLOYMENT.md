# GitHub-native deployment guide

This project uses GitHub as the source-of-truth and CI/CD platform. GitHub Pages hosts the static Next.js export. A Cloudflare Worker provides the server-side AI API; GitHub Pages cannot execute a private API key or server-side route.

## 1. Make the repository public

The repository must be public to use GitHub Pages on GitHub Free. In GitHub, open **Settings → General → Danger Zone → Change repository visibility → Make public** and confirm. Publishing the repository also makes its source code publicly readable. Never commit credentials, .env files, student records, or private study material.

## 2. Enable GitHub Pages

Open **Settings → Pages → Build and deployment → Source**, select **GitHub Actions**, and save. The workflow in .github/workflows/deploy-pages.yml builds the Next.js static export and publishes out/.

Expected site URL: https://omendi-atlan.github.io/examgen-ai/.

## 3. Create the external AI API

Create a Cloudflare account and open **Workers & Pages**. The Worker source is in worker/src/index.ts; its configuration is worker/wrangler.toml. Add these GitHub repository Actions secrets under **Settings → Secrets and variables → Actions → New repository secret**:

- CLOUDFLARE_API_TOKEN: a Cloudflare API token with permission to deploy Workers.
- CLOUDFLARE_ACCOUNT_ID: the Cloudflare account ID.

Add the OpenAI key as a Worker secret, not as a GitHub Pages variable and not in source code. In the Cloudflare dashboard, open the deployed Worker → **Settings → Variables and Secrets → Add → Secret**; set the name to OPENAI_API_KEY and the value to the newly rotated key. The optional model is configured as OPENAI_MODEL in worker/wrangler.toml.

The Worker is deployed by .github/workflows/deploy-worker.yml when worker/ changes or when manually run from **Actions → Deploy AI Worker → Run workflow**. The first deployment requires the two Cloudflare GitHub secrets above.

## 4. Connect the website to the Worker

After deployment, copy the Worker URL, normally https://examgen-ai-api.<your-workers-subdomain>.workers.dev. In GitHub, open **Settings → Secrets and variables → Actions → Variables → New repository variable** and add:

- Name: NEXT_PUBLIC_EXAMGEN_API_URL
- Value: the Worker base URL, with no trailing slash.

The Pages workflow embeds this public API URL at build time. Re-run **Deploy GitHub Pages** from the Actions tab after setting the variable (or push a new commit to main).

## 5. Verify deployment

In **Actions**, confirm both Deploy AI Worker and Deploy GitHub Pages complete successfully. Open the Pages URL, generate a small practice assessment, then test simulation mode. If API calls fail, check the Worker deployment, its OPENAI_API_KEY secret, the ALLOWED_ORIGIN value, and the NEXT_PUBLIC_EXAMGEN_API_URL repository variable.

## Current scope and limitations

- The website is statically hosted by GitHub Pages; the Worker is the only external runtime service.
- Student accounts and persistent exam history are deferred.
- Practice generation currently returns study guidance to the browser. Simulation generation strips answer keys before returning the paper; secure server-side marking and durable exam sessions are future work.
- Written answers still need a rubric-based marking workflow. The current foundation does not claim fully automated marking.
- Source-document ingestion, question-bank persistence, adaptive revision, PDF export, and visual generation/approval are roadmap items, not completed features.
- The public repository contains application source. Do not place confidential content or secrets in it.
