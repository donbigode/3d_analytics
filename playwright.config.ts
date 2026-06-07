import { defineConfig } from "@playwright/test";

/**
 * Playwright config for the 3D Print Orçamento & Analítico happy-path E2E.
 *
 * Pre-requisites (handled by `make e2e`):
 *   1. `make up`  — stack docker (API + Postgres) running on :8000
 *   2. `make seed` — default user t@t.com/pw exists
 *   3. Playwright spawns `npm run dev` for the frontend on :5173
 *      (vite proxies /api → :8000).
 */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    ignoreHTTPSErrors: true,
  },
  webServer: {
    command: "npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
