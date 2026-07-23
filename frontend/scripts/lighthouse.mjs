#!/usr/bin/env node
// Lighthouse CI against a local preview build (WS7.9). `lighthouse` is deliberately NOT a
// package.json dependency — it's a heavy, occasionally-used dev tool, and `npx lighthouse`
// already fetches it on demand. This script just wires it to our build + budget.json when it's
// available, and otherwise prints how to run it instead of failing or faking a result.
//
// Usage: npm run build && npm run lighthouse

import { spawn, spawnSync } from "node:child_process";

const PORT = 4173;
const URL = `http://localhost:${PORT}/today`;

// `npx --no-install` finds a PATH-installed lighthouse AND the npx cache (how this machine has
// it) without ever downloading one inside a "check" — the download decision stays with a human.
const hasLighthouse = spawnSync("npx", ["--no-install", "lighthouse", "--version"]).status === 0;

if (!hasLighthouse) {
  console.log(
    [
      "",
      "`lighthouse` isn't installed, so this check is skipped rather than faked.",
      "It is intentionally not a dependency of this project (WS7.9 — 'do not add it as a",
      "dependency, document instead'). To run it locally:",
      "",
      "  npm run build",
      "  npm run preview -- --port 4173 &",
      `  npx lighthouse ${URL} --budget-path=budget.json --preset=perf --view`,
      "",
      "npx fetches lighthouse on demand; nothing needs installing ahead of time.",
      "",
    ].join("\n"),
  );
  process.exit(0);
}

async function waitForServer(url, timeoutMs = 15_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.ok || res.status === 404) return; // server is up, even if this exact path 404s
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`preview server did not come up at ${url} within ${timeoutMs}ms`);
}

const preview = spawn("npx", ["vite", "preview", "--port", String(PORT), "--strictPort"], {
  stdio: "inherit",
});

try {
  await waitForServer(`http://localhost:${PORT}/`);
  const result = spawnSync(
    "npx",
    [
      "--no-install",
      "lighthouse",
      URL,
      // Lighthouse ≥ 12 ignores --budget-path (kept for older CLIs); compare the printed
      // resource/LCP numbers against budget.json yourself — see frontend/README.md.
      "--budget-path=budget.json",
      "--preset=perf",
      "--quiet",
      // headless so the check runs on CI boxes and over ssh, not only at a desktop session
      "--chrome-flags=--headless=new",
    ],
    { stdio: "inherit" },
  );
  process.exitCode = result.status ?? 1;
} finally {
  preview.kill();
}
