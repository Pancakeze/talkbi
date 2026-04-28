import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry"
  },
  projects: [
    {
      name: "chrome",
      use: { ...devices["Desktop Chrome"] }
    }
  ],
  webServer: [
    {
      command:
        "bash -lc 'cd ../api && rm -f ./talkbi.e2e.db && if [ -x ./.venv/bin/python ]; then PY=./.venv/bin/python; else PY=python; fi; DATABASE_URL=sqlite+pysqlite:///./talkbi.e2e.db $PY -m uvicorn app.main:app --host 127.0.0.1 --port 8000'",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: !process.env.CI
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI
    }
  ]
});
