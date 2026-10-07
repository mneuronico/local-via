import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.E2E_PORT ?? 8091);

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  workers: 1,
  use: { baseURL: `http://localhost:${port}`, trace: "retain-on-failure", screenshot: "only-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  outputDir: "test-results",
  // A real hub with one mock worker (no GPU). Requires `npm run build` and the .venv from requirements-dev.txt.
  webServer: {
    command: `${process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python"} scripts/dev_classroom.py --workers 1 --port ${port} --mock-seconds 4 --reset --data-dir data/e2e-classroom`,
    url: `http://localhost:${port}/healthz`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
