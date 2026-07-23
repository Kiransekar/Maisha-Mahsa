// QG.2 — Playwright E2E against the REAL local stack. `npm run test:e2e` (or `make e2e-frontend`
// at the repo root) starts everything itself via e2e/stack.mjs: real Mahsa binary, real FastAPI
// on a fresh seeded SQLite, the real Vite-served SPA, and the Better Auth stand-in (see
// e2e/stack.mjs for why auth — and ONLY auth — is a test double; the API still verifies every
// JWT against a real JWKS endpoint).
//
// NOT part of scripts/ci_gate.sh — adding a 20th gate step is an ORCH decision (§1 working
// agreement); this suite is authored, wired and ready to gate (see PROGRESS.md [QG.2+MED-2]).
//
// Chromium only, on purpose: QG.2 mandates per-hub happy paths + approval flows, not a
// cross-browser matrix. Widen `projects` when a real browser-specific defect motivates it.

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  // The suite drives ONE shared backend with real, stateful books (an approval writes a
  // permanent audit entry) — serial keeps every spec's preconditions honest.
  fullyParallel: false,
  workers: 1,
  retries: 0, // a flake is a defect here, not a statistic
  use: {
    baseURL: "http://127.0.0.1:5183",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "node e2e/stack.mjs",
    url: "http://127.0.0.1:5183",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
