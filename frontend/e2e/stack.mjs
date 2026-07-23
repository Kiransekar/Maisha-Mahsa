#!/usr/bin/env node
// QG.2 — the E2E stack, started by playwright.config.ts's webServer. One process that brings up
// the REAL product loop end to end and dies with everything it started:
//
//   auth stand-in (this file, in-process)      :8791   JWKS + sign-in + get-session + /token
//   Mahsa (real Rust binary, dif/target)       :8792   the recompute gatekeeper — never stubbed
//   Maisha API (real uvicorn, app.main:app)    :8793   fresh seeded SQLite per run
//   Vite dev server (the actual SPA)           :5183   /api/auth -> stand-in, /api -> Maisha
//
// WHY a stand-in for auth and nothing else: the Better Auth server is the OWNER'S Node service
// (see src/lib/auth.ts — its config lives outside this repo), so it cannot be started here. The
// stand-in mirrors exactly what api/tests/conftest.py's `betterauth_owner_env` fixture does for
// the backend suite: a real Ed25519 JWKS endpoint plus JWTs carrying the claims the API demands
// (sub/email/iss/aud/activeOrganizationId/role). The API's verification path — PyJWKClient
// against the JWKS URL, signature, iss, aud, exp — runs FOR REAL on every request; only the
// token MINTER is a test double. Credentials: owner@example.com / e2e-password.
//
// Ports are fixed (not ephemeral) so playwright.config.ts can name its webServer URL; they are
// deliberately offset from the dev defaults (5173/8000) so `make dev` and E2E can coexist.

import { spawn } from "node:child_process";
import { generateKeyPairSync, randomUUID, sign as edSign } from "node:crypto";
import { createServer } from "node:http";
import { existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const AUTH_PORT = 8791;
const MAHSA_PORT = 8792;
const API_PORT = 8793;
const WEB_PORT = 5183;
const AUTH_BASE = `http://127.0.0.1:${AUTH_PORT}`;

export const E2E_EMAIL = "owner@example.com";
export const E2E_PASSWORD = "e2e-password";

// ── auth stand-in ───────────────────────────────────────────────────────────────────────────────

const { publicKey, privateKey } = generateKeyPairSync("ed25519");
const KID = `e2e-kid-${randomUUID()}`;
const jwk = { ...publicKey.export({ format: "jwk" }), kid: KID, use: "sig", alg: "EdDSA" };

const b64u = (input) => Buffer.from(input).toString("base64url");

function mintJwt() {
  const now = Math.floor(Date.now() / 1000);
  const header = b64u(JSON.stringify({ alg: "EdDSA", typ: "JWT", kid: KID }));
  const payload = b64u(
    JSON.stringify({
      sub: "u-owner",
      email: E2E_EMAIL,
      iss: AUTH_BASE,
      aud: AUTH_BASE,
      iat: now,
      exp: now + 3600,
      activeOrganizationId: "org-e2e",
      role: "owner",
    }),
  );
  const sig = edSign(null, Buffer.from(`${header}.${payload}`), privateKey);
  return `${header}.${payload}.${b64u(sig)}`;
}

const SESSION_COOKIE = "maisha_e2e_session";
const hasSession = (req) => (req.headers.cookie ?? "").includes(`${SESSION_COOKIE}=1`);

function json(res, status, body, extraHeaders = {}) {
  const data = JSON.stringify(body);
  res.writeHead(status, { "content-type": "application/json", ...extraHeaders });
  res.end(data);
}

const authServer = createServer((req, res) => {
  const path = new URL(req.url, AUTH_BASE).pathname;

  if (req.method === "GET" && path === "/api/auth/jwks") {
    return json(res, 200, { keys: [jwk] });
  }
  if (req.method === "POST" && path === "/api/auth/sign-in/email") {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", () => {
      let body = {};
      try {
        body = JSON.parse(raw);
      } catch {
        /* fall through to the credential check */
      }
      if (body.email === E2E_EMAIL && body.password === E2E_PASSWORD) {
        return json(
          res,
          200,
          { redirect: false, token: "e2e-session", user: { id: "u-owner", email: E2E_EMAIL, name: "Owner" } },
          { "set-cookie": `${SESSION_COOKIE}=1; Path=/; HttpOnly; SameSite=Lax` },
        );
      }
      return json(res, 401, { code: "INVALID_EMAIL_OR_PASSWORD", message: "Invalid email or password" });
    });
    return;
  }
  if (req.method === "GET" && path === "/api/auth/get-session") {
    if (!hasSession(req)) return json(res, 200, null);
    return json(res, 200, {
      session: {
        id: "s-e2e",
        userId: "u-owner",
        activeOrganizationId: "org-e2e",
        expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
      },
      user: { id: "u-owner", email: E2E_EMAIL, name: "Owner" },
    });
  }
  if (req.method === "GET" && path === "/api/auth/token") {
    if (!hasSession(req)) return json(res, 401, { message: "unauthenticated" });
    return json(res, 200, { token: mintJwt() });
  }
  if (req.method === "POST" && path === "/api/auth/sign-out") {
    return json(res, 200, { success: true }, { "set-cookie": `${SESSION_COOKIE}=; Path=/; Max-Age=0` });
  }
  // Anything else (organization/list etc.): an honest empty answer, never a 500 — the SPA
  // treats null data as "no orgs / no session", which is the truthful stand-in state.
  return json(res, 200, null);
});

// ── child processes ─────────────────────────────────────────────────────────────────────────────

const children = [];
function run(name, cmd, args, opts) {
  const child = spawn(cmd, args, { stdio: ["ignore", "inherit", "inherit"], ...opts });
  child.on("exit", (code) => {
    // any leg dying means the stack is not the stack — fail loudly, kill the rest
    if (!shuttingDown) {
      console.error(`[e2e-stack] ${name} exited (${code}) — tearing down`);
      shutdown(1);
    }
  });
  children.push(child);
  return child;
}

let shuttingDown = false;
function shutdown(code) {
  if (shuttingDown) return;
  shuttingDown = true;
  for (const c of children) c.kill("SIGTERM");
  authServer.close();
  process.exitCode = code;
  // give children a moment, then hard-exit so playwright's webServer teardown never hangs
  setTimeout(() => process.exit(code), 3000).unref();
}
process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

async function waitFor(url, name, timeoutMs = 60_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.status < 500) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  console.error(`[e2e-stack] ${name} did not come up at ${url} within ${timeoutMs}ms`);
  shutdown(1);
  throw new Error(`${name} unavailable`);
}

// ── bring-up ────────────────────────────────────────────────────────────────────────────────────

const mahsaBin = ["debug", "release"]
  .map((p) => join(ROOT, "dif", "target", p, "mahsa"))
  .find(existsSync);
if (!mahsaBin) {
  console.error("[e2e-stack] no mahsa binary — run `cargo build` in dif/ first. E2E never stubs Mahsa.");
  process.exit(1);
}
const venvPy = join(ROOT, "api", ".venv", "bin", "python");
if (!existsSync(venvPy)) {
  console.error("[e2e-stack] no api/.venv — run `make venv` first.");
  process.exit(1);
}

// fresh, throwaway DB per run — E2E must never depend on (or dirty) the dev database
const tmpDir = join(ROOT, "frontend", "e2e", ".tmp");
rmSync(tmpDir, { recursive: true, force: true });
mkdirSync(tmpDir, { recursive: true });
const dbUrl = `sqlite:///${join(tmpDir, "maisha-e2e.db")}`;

const apiEnv = {
  ...process.env,
  MAISHA_DATABASE_URL: dbUrl,
  MAISHA_MAHSA_URL: `http://127.0.0.1:${MAHSA_PORT}`,
  MAISHA_BETTER_AUTH_URL: AUTH_BASE,
  MAISHA_ENVIRONMENT: "development",
  // Must match the JWT's activeOrganizationId ("org-e2e"): the seed's memory/audit-chain rows
  // are org-scoped and would be invisible to the signed-in E2E user under the default demo-org.
  MAISHA_SEED_ORG_ID: "org-e2e",
};

authServer.listen(AUTH_PORT, "127.0.0.1");

// seed BEFORE the API starts (same sample company `make seed` loads)
const seed = spawn(venvPy, ["-m", "app.dev.seed"], {
  cwd: join(ROOT, "api"),
  env: apiEnv,
  stdio: ["ignore", "inherit", "inherit"],
});
await new Promise((res, rej) =>
  seed.on("exit", (code) => (code === 0 ? res() : rej(new Error(`seed exited ${code}`)))),
);

run("mahsa", mahsaBin, [], { env: { ...process.env, MAHSA_ADDR: `127.0.0.1:${MAHSA_PORT}` } });
run("api", venvPy, ["-m", "uvicorn", "app.main:app", "--port", String(API_PORT), "--host", "127.0.0.1"], {
  cwd: join(ROOT, "api"),
  env: apiEnv,
});
await waitFor(`http://127.0.0.1:${MAHSA_PORT}/health`, "mahsa");
await waitFor(`http://127.0.0.1:${API_PORT}/api/health/connections`, "api");

run("vite", "npx", ["vite", "--port", String(WEB_PORT), "--strictPort", "--host", "127.0.0.1"], {
  cwd: join(ROOT, "frontend"),
  env: {
    ...process.env,
    // E2E_API_TARGET, NOT VITE_API_BASE: a VITE_-prefixed var is exposed to the client bundle,
    // where lib/api.ts would use it as a cross-origin base and every call would fail on CORS.
    // The client must stay same-origin ("" base) so requests flow through the vite proxy.
    E2E_API_TARGET: `http://127.0.0.1:${API_PORT}`,
    E2E_AUTH_STUB: AUTH_BASE,
  },
});
await waitFor(`http://127.0.0.1:${WEB_PORT}/`, "vite");
console.log(`[e2e-stack] up — SPA http://127.0.0.1:${WEB_PORT} · api :${API_PORT} · mahsa :${MAHSA_PORT} · auth :${AUTH_PORT}`);
