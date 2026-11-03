import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    include: ["worker/tests/integration/**/*.integration.test.mjs"],
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          bindings: { OPENAI_API_KEY: "integration-test-key" }
        }
      }
    }
  }
});
