// defineConfig from vitest/config (a typed superset of vite's) so the `test` block typechecks.
import { configDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The SPA talks to the backend over a JSON API. In dev we proxy /api -> FastAPI (the correct,
// recompute-gated backend); the same VITE_API_BASE swaps to NestJS later without UI changes.
//
// QG.2 E2E: the Better Auth server is the owner's own Node service and is not in this repo, so
// the E2E stack (e2e/stack.mjs) runs a test stand-in (JWKS + sign-in + /token) and points
// E2E_AUTH_STUB at it. The key ORDER matters — "/api/auth" must be matched before "/api" (vite
// tries proxy rules in insertion order), which is why the auth rule is spread in first.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    // Playwright specs live in e2e/ and match vitest's default *.spec.ts glob — they need a
    // running stack + browser, so vitest must never collect them. Environment stays "node"
    // (the pure/renderToStaticMarkup suites); mounted tests opt into jsdom per-file via the
    // `// @vitest-environment jsdom` pragma (MED-2).
    exclude: [...configDefaults.exclude, "e2e/**"],
  },
  server: {
    proxy: {
      ...(process.env.E2E_AUTH_STUB
        ? { "/api/auth": { target: process.env.E2E_AUTH_STUB, changeOrigin: true } }
        : {}),
      // E2E_API_TARGET is SERVER-ONLY (never leaks into the client bundle the way VITE_* vars
      // do) — the E2E stack must proxy same-origin, or the SPA would call the API cross-origin
      // and every request would die on CORS instead of exercising the real path.
      "/api": {
        target: process.env.E2E_API_TARGET || process.env.VITE_API_BASE || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
