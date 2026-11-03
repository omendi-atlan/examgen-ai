import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    include: ["worker/tests/integration/**/*.integration.test.mjs"],
    poolOptions: {
      workers: {
        wrangler: { configPath: "./worker/wrangler.toml" }
      }
    }
  }
});
