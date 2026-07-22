// WS4.3 — the client half of Better Auth. The owner runs and configures the Better Auth server;
// this file only wires the SPA to it, through the OFFICIAL React client (better-auth/react) — no
// hand-rolled sign-in fetch, no hand-rolled credential handling.
//
// baseURL is env-driven, mirroring the VITE_API_BASE seam in lib/api.ts (never hardcode a URL).
//
// ─────────────────────────────────────────────────────────────────────────────────────────────
// THE TRUST-BOUNDARY SEAM (this file's whole reason to exist)
//
// The previous revision sent `data.session.token` — Better Auth's OPAQUE SESSION ID — to an API
// (api/app/core/betterauth.py) that verifies a JWKS-signed JWT. Those two are different objects
// from different systems; the API's `decode_claims` would have raised DecodeError on every single
// request. The seam was inert: no authenticated call could ever have succeeded.
//
// The fix: get an ACTUAL JWT. Better Auth's jwt plugin exposes `GET {BASE}/api/auth/token`
// (verified in node_modules/better-auth/dist/plugins/jwt/index.mjs:128 — `createAuthEndpoint(
// "/token", { method: "GET", use: [sessionMiddleware] })` returning `ctx.json({ token })`). It
// authenticates with the session cookie, which is why `credentials: "include"` is mandatory.
// The API then verifies that JWT against `{BASE}/api/auth/jwks` — the exact URL
// `betterauth.better_auth_jwks_url()` builds.
//
// ⚠️ OWNER ACTION REQUIRED — SERVER-SIDE CONFIG THIS REPO CANNOT SEE OR SUPPLY.
// The API demands claims that Better Auth's DEFAULT payload does not contain. The default is
// literally `ctx.context.session.user` (jwt/sign.mjs:53), i.e. the user row only. The API
// requires, and denies without:
//   · `activeOrganizationId`  → api/app/core/betterauth.py ACTIVE_ORG_CLAIM; absent ⇒ 403.
//   · `role`                  → ROLE_CLAIM, mapped by principal.map_better_auth_role; absent or
//                               unmapped ⇒ 403.
//   · `email`                 → decode_claims rejects a token without it ⇒ 401.
// Both org fields live on the SESSION (organization plugin), not on the user, so they only reach
// the token via an explicit `definePayload`:
//
//   betterAuth({
//     plugins: [
//       organization(),
//       twoFactor(),
//       jwt({ jwt: { definePayload: async ({ user, session }) => ({
//         sub: user.id,
//         email: user.email,
//         activeOrganizationId: session.activeOrganizationId,
//         role: /* the caller's role in that org — read the member row */,
//         // and, ONLY once you have wired it, the MFA claim named by
//         // MAISHA_BETTER_AUTH_MFA_CLAIM (see assert_mfa_satisfied); until then the API's
//         // MFA policy is documented-but-not-enforced, by design.
//       }) } }),
//     ],
//   })
//
// This is stated rather than guessed on purpose: inventing a claim shape here would produce a
// client that looks wired and 403s in production.
// ─────────────────────────────────────────────────────────────────────────────────────────────
import { createAuthClient } from "better-auth/react";
import { organizationClient, twoFactorClient } from "better-auth/client/plugins";

const BASE = import.meta.env.VITE_BETTER_AUTH_URL ?? "";

// ponytail: no jwtClient() plugin — its only action is `jwks`, which the FastAPI side fetches
// itself (PyJWKClient). The SPA needs the /token endpoint, and $fetch already reaches it.
export const authClient = createAuthClient({
  baseURL: BASE,
  plugins: [organizationClient(), twoFactorClient()],
  // better-auth captures `fetch` once, at import time (better-auth/dist/client/config.mjs:45
  // `customFetchImpl: fetch`). Late-bind it instead, so anything installed after module load —
  // a test double, a service worker, an instrumentation wrapper — is actually used rather than
  // silently bypassed. Same behaviour in the browser; the difference is only *when* fetch is read.
  fetchOptions: {
    customFetchImpl: (input, init) => globalThis.fetch(input as RequestInfo, init as RequestInit),
  },
});

// Re-exported as-is — components call these directly, same as any other better-auth consumer.
export const { useSession, useActiveOrganization, useListOrganizations } = authClient;

export type SessionState = "loading" | "guest" | "authed";

/** The one auth gate every protected route needs. `isPending` MUST win over `data` being absent
 * — better-auth starts a session check with `data: null, isPending: true`, and treating that as
 * "guest" would flash every authenticated user to /sign-in on first paint. */
export function sessionStatus(data: unknown, isPending: boolean): SessionState {
  if (isPending) return "loading";
  return data ? "authed" : "guest";
}

// ── JWT cache ────────────────────────────────────────────────────────────────────────────────
// One token fetch per token lifetime, not one per API call. Cached in a module variable (never
// localStorage: a bearer token in localStorage is readable by any XSS on the page, and the
// session cookie it is minted from is already HttpOnly — putting the derived credential
// somewhere weaker than its source would be a downgrade).

type CachedToken = { token: string; expiresAtMs: number };

let cached: CachedToken | null = null;

/** Refresh this far BEFORE `exp` so a token can't expire in flight between here and the API. */
export const EXPIRY_SKEW_MS = 30_000;

/**
 * `exp` (epoch ms) out of a JWT's payload segment, or 0 when it cannot be read.
 *
 * Read-only parsing for CACHE LIFETIME ONLY. This is NOT verification and must never be treated
 * as such — the signature, `iss`, `aud` and `exp` are all checked by the API against JWKS
 * (api/app/core/betterauth.py::decode_claims). Nothing here decides whether a token is trusted;
 * it only decides when to ask for a fresh one.
 *
 * 0 on anything unreadable, which `isTokenUsable` treats as unusable — an opaque or malformed
 * token is refetched every call rather than cached forever. That is the fail-safe direction, and
 * it is what would have caught the previous revision's session-id-as-JWT bug at runtime.
 */
export function jwtExpiryMs(token: string): number {
  const payload = token.split(".")[1];
  if (!payload) return 0;
  try {
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const claims: unknown = JSON.parse(json);
    const exp = (claims as { exp?: unknown })?.exp;
    return typeof exp === "number" ? exp * 1000 : 0;
  } catch {
    return 0;
  }
}

/** Is a cached token still safe to send? Pure, so the skew logic is directly testable. */
export function isTokenUsable(entry: CachedToken | null, nowMs: number): boolean {
  return entry !== null && entry.expiresAtMs - EXPIRY_SKEW_MS > nowMs;
}

/**
 * Drop the cached JWT. Called on sign-out, on org switch (the token carries
 * `activeOrganizationId` — a stale one would keep addressing the OLD org after the switch), and
 * by lib/api.ts on any 401 (the API told us this token is no longer good; keeping it would loop).
 */
export function clearAuthToken(): void {
  cached = null;
}

/** The current session's JWT, minted by Better Auth's jwt plugin, or null when signed out. */
export async function getAuthToken(): Promise<string | null> {
  const now = Date.now();
  if (isTokenUsable(cached, now)) return cached!.token;
  cached = null;
  let token: unknown;
  try {
    // credentials:"include" — /token authenticates with the HttpOnly session cookie.
    const res = await fetch(`${BASE}/api/auth/token`, {
      method: "GET",
      credentials: "include",
      headers: { accept: "application/json" },
    });
    if (!res.ok) return null; // signed out (401) or plugin not enabled (404). Never throws.
    token = ((await res.json()) as { token?: unknown })?.token;
  } catch {
    return null; // auth server unreachable — an anonymous call, not a fabricated header.
  }
  if (typeof token !== "string" || token === "") return null;
  cached = { token, expiresAtMs: jwtExpiryMs(token) };
  return token;
}

/**
 * The Authorization header lib/api.ts puts on every backend call.
 *
 * Header form matches `betterauth.bearer_token()` exactly: `Authorization: Bearer <jwt>`.
 * Returns `{}` — never a fabricated header — when there is no session, so an anonymous call is
 * simply anonymous and the API's fail-closed middleware answers 401.
 */
export async function authHeaders(): Promise<Record<string, string>> {
  const token = await getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Sign out AND drop the cached JWT — a bearer token outliving its session is a live credential. */
export async function signOut(): Promise<void> {
  clearAuthToken();
  await authClient.signOut();
}

/** Guards the cache-clear in `switchOrganization` below: only a real change warrants it. */
export function shouldSwitchOrganization(
  activeOrganizationId: string | null | undefined,
  targetOrganizationId: string,
): boolean {
  return activeOrganizationId !== targetOrganizationId;
}

/**
 * Organization switching MUST clear every cached query — showing org A's cash balance under org
 * B's name is a cross-tenant leak to the user's own eyes, not a cosmetic bug (ticket invariant).
 * `queryClient.clear()`, not `invalidateQueries()`: invalidate still serves the stale cached data
 * for one paint while refetching, which is exactly the leak this exists to prevent.
 *
 * `clearAuthToken()` is the other half and is just as load-bearing: the JWT carries
 * `activeOrganizationId`, which the API turns into the RLS `app.current_org` GUC. Keeping the old
 * token would silently keep every query scoped to the PREVIOUS org while the UI names the new one
 * — the same leak, one layer down, and the one the cache-clear alone does not close.
 */
export async function switchOrganization(
  queryClient: { clear: () => void },
  activeOrganizationId: string | null | undefined,
  targetOrganizationId: string,
): Promise<void> {
  if (!shouldSwitchOrganization(activeOrganizationId, targetOrganizationId)) return;
  await authClient.organization.setActive({ organizationId: targetOrganizationId });
  clearAuthToken();
  queryClient.clear();
}
