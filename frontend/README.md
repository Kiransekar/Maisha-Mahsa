# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.

## Testing (QG.2 + MED-2)

Three layers, each with its own command:

- `npm run test` — vitest. Pure-helper and `renderToStaticMarkup` suites run in the default
  node environment; mounted component suites (`*.mount.test.tsx`, jsdom + @testing-library/react)
  opt in per-file via the `// @vitest-environment jsdom` pragma. Playwright specs in `e2e/` are
  excluded from vitest (see `test.exclude` in vite.config.ts).
- `npm run test:e2e` — Playwright browser E2E (`make e2e-frontend` from the repo root). Starts
  the full real stack itself via `e2e/stack.mjs` (real Mahsa binary, real FastAPI on a fresh
  seeded SQLite, the Vite-served SPA, and a Better Auth stand-in whose JWTs the API verifies
  against a real JWKS endpoint — see stack.mjs for the rationale). Prereqs: `make venv`,
  `cargo build` in `dif/`, and `npx playwright install chromium`. Deliberately NOT part of
  `scripts/ci_gate.sh` yet — promoting it to a gate step is an ORCH decision.
- `npm run lighthouse` — perf budget (`budget.json`: script ≤ 300 KB, total ≤ 600 KB,
  LCP ≤ 2500 ms). Status from the 2026-07-23 WS7.9-perf fix (Lighthouse 12.8, headless Chrome,
  mobile throttling, production build served by `vite preview`, target `/today` as a guest —
  the session-check → /sign-in redirect path):
  - **ALL budgets PASS**: LCP **1263–1330 ms** across 4 runs (budget 2500 ms), initial-route
    script 102.7 KB transfer (budget 300), total 110.5 KB (budget 600), perf score 0.99;
  - before the fix the same runs measured LCP 2.4–3.0 s (median ~2.9 s; an earlier run on a
    loaded machine recorded 11.2 s — not reproducible since, but the budget breach was real).
    Two root causes, both fixed: (1) a single 510 KB/146 KB-gzip bundle had to download AND
    parse before any paint — every authenticated screen is now a `lazy()` route-level chunk
    (`src/App.tsx`; entry is 334 KB/106 KB gzip; SignIn stays eager because it IS the guest LCP
    path); (2) nothing painted until React mounted — `index.html` now carries a static app-shell
    first paint (inlined styles, product name + the recompute-promise sentence; NO figures, no
    data-shaped chrome per anti-pattern #14), so first paint no longer waits on script parse or
    the session roundtrip;
  - Lighthouse ≥ 12 REMOVED the `--budget-path` budget audits, so `budget.json` is no longer
    asserted by lighthouse itself — compare the printed resource-summary/LCP numbers against
    budget.json yourself (or via lighthouse-ci `assertions` if/when CI adopts it);
  - the script now finds the npx-cached lighthouse (not just a PATH install) and runs Chrome
    headless, so it works on CI boxes and over ssh; the HTML report lands in `frontend/` and is
    gitignored (`*.report.html`).
