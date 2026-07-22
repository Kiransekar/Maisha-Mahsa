// Two kinds of test here, deliberately:
//
//  1. PURE logic — the session gate, the cache-clear guard, the JWT cache lifetime.
//  2. RENDERED-ROUTE tests that mount the REAL <App/> (real react-router, real RequireAuth, real
//     route table) and assert on the actual output. These exist because the reviewable claim is
//     "an unauthenticated visitor cannot reach a financial figure", and a unit test against an
//     invented contract cannot show that. `renderToStaticMarkup` is enough to prove it and needs
//     no jsdom/testing-library (ponytail: no new devDependency for a string comparison).
//
// The mutation that must kill these: deleting the `status === "guest"` redirect in RequireAuth.
// The pure tests survive that. The render tests do not — which is the whole point.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// In a browser an empty baseURL means "same origin"; under vitest's node environment there is no
// origin to resolve against, so better-fetch rejects the relative URL. Set before lib/auth is
// imported (hoisted above the import graph) — this is test plumbing, not behaviour.
vi.hoisted(() => {
  vi.stubEnv("VITE_BETTER_AUTH_URL", "https://auth.test");
});

// Only `useSession` is faked — everything else in lib/auth (sessionStatus, the gate logic App
// actually runs) stays real. Mocking the gate itself would prove nothing.
const sessionMock = vi.hoisted(() => ({
  current: { data: null as unknown, isPending: false },
}));

vi.mock("./auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./auth")>()),
  useSession: () => sessionMock.current,
  useActiveOrganization: () => ({ data: null }),
  useListOrganizations: () => ({ data: [] }),
}));

import { App } from "../App";
import { ApiError, api } from "./api";
import { needsSecondFactor } from "../routes/SignIn";
import {
  EXPIRY_SKEW_MS,
  authHeaders,
  clearAuthToken,
  isTokenUsable,
  jwtExpiryMs,
  sessionStatus,
  shouldSwitchOrganization,
  switchOrganization,
} from "./auth";

function renderAt(path: string): string {
  return renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
      createElement(MemoryRouter, { initialEntries: [path] }, createElement(App)),
    ),
  );
}

/** A JWT-shaped string with a real payload segment. Unsigned — nothing client-side verifies it. */
function fakeJwt(claims: Record<string, unknown>): string {
  const b64 = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${b64({ alg: "EdDSA", typ: "JWT" })}.${b64(claims)}.sig`;
}

// Every protected route in the app. If a route is added without a gate, add it here too.
const PROTECTED = ["/today", "/inbox", "/approvals", "/domains", "/d/treasury", "/audit", "/onboarding", "/"];

describe("route gating — a guest must not reach a protected route", () => {
  beforeEach(() => {
    sessionMock.current = { data: null, isPending: false };
    clearAuthToken();
  });

  it.each(PROTECTED)("redirects a signed-out visitor away from %s", (path) => {
    sessionMock.current = { data: null, isPending: false };
    const html = renderAt(path);
    // <Navigate> renders nothing, so the protected view's own chrome must be absent. The Shell's
    // nav is the cheapest unambiguous marker that we are inside the authenticated app.
    expect(html).not.toContain("Exception Inbox");
    expect(html).not.toContain("Audit Room");
    expect(html).not.toContain("recomputed by a second engine");
  });

  it("renders the authenticated shell for a signed-in user (the other direction)", () => {
    sessionMock.current = { data: { user: { id: "u1" } }, isPending: false };
    const html = renderAt("/today");
    expect(html).toContain("Exception Inbox");
    expect(html).toContain("Audit Room");
  });

  it("shows a session message, never a data-shaped skeleton, while the check is in flight", () => {
    sessionMock.current = { data: null, isPending: true };
    const html = renderAt("/today");
    expect(html).toContain("Checking your session");
    // Anti-pattern #14: an indeterminate state must not look like the ledger loading.
    expect(html).not.toContain("Exception Inbox");
  });

  it("serves /sign-in to a guest without the authenticated shell", () => {
    sessionMock.current = { data: null, isPending: false };
    const html = renderAt("/sign-in");
    expect(html).toContain("Sign in");
    expect(html).not.toContain("Exception Inbox");
  });
});

describe("sessionStatus — the loading/guest/authed gate", () => {
  it("is 'loading' while a session check is in flight, regardless of data", () => {
    expect(sessionStatus(null, true)).toBe("loading");
    expect(sessionStatus({ user: {} }, true)).toBe("loading");
  });

  it("is 'authed' once resolved with session data", () => {
    expect(sessionStatus({ user: { id: "u1" } }, false)).toBe("authed");
  });

  it("is 'guest' once resolved with no session data", () => {
    expect(sessionStatus(null, false)).toBe("guest");
    expect(sessionStatus(undefined, false)).toBe("guest");
  });

  it("never reads a resolving check's null data as 'guest' (would bounce a real session)", () => {
    expect(sessionStatus(null, true)).not.toBe("guest");
  });
});

describe("needsSecondFactor — a 2FA challenge is not a completed sign-in", () => {
  it("is true for Better Auth's twoFactorRedirect payload", () => {
    expect(needsSecondFactor({ twoFactorRedirect: true })).toBe(true);
  });

  it("is false for a real session payload, so a 1FA account is not stranded on a code form", () => {
    expect(needsSecondFactor({ user: { id: "u1" }, token: "s" })).toBe(false);
    expect(needsSecondFactor({ twoFactorRedirect: false })).toBe(false);
    expect(needsSecondFactor(null)).toBe(false);
    expect(needsSecondFactor(undefined)).toBe(false);
  });
});

describe("api() — every backend call actually carries the JWT", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    clearAuthToken();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  const token = () => fakeJwt({ sub: "u1", exp: Math.floor(Date.now() / 1000) + 3600 });

  /** First call answers /api/auth/token, the rest answer the backend. */
  function wire(jwt: string, backend: Partial<Response> & { status: number }) {
    fetchMock
      .mockResolvedValueOnce({ ok: true, json: async () => ({ token: jwt }) })
      .mockResolvedValue({ ok: backend.status < 400, ...backend, json: async () => ({}) });
  }

  it("attaches Authorization: Bearer <jwt> on a GET", async () => {
    const jwt = token();
    wire(jwt, { status: 200 });
    await api("/today");
    const [, init] = fetchMock.mock.calls[1];
    expect(init.headers.Authorization).toBe(`Bearer ${jwt}`);
  });

  it("keeps BOTH the JWT and content-type when the caller passes its own headers", async () => {
    const jwt = token();
    wire(jwt, { status: 200 });
    // The regression: `...init` spread AFTER `headers` let init.headers replace the whole merged
    // object, silently stripping Authorization from every request that sends a body.
    await api("/approvals/gst/decide", {
      method: "POST",
      body: "{}",
      headers: { "x-trace": "t1" },
    });
    const [, init] = fetchMock.mock.calls[1];
    expect(init.headers.Authorization).toBe(`Bearer ${jwt}`);
    expect(init.headers["content-type"]).toBe("application/json");
    expect(init.headers["x-trace"]).toBe("t1");
    expect(init.method).toBe("POST");
  });

  it("drops the cached token on a 401 so the next call re-mints instead of replaying a dead one", async () => {
    const first = token();
    wire(first, { status: 401, statusText: "Unauthorized" });
    await expect(api("/today")).rejects.toBeInstanceOf(ApiError);

    const second = fakeJwt({ sub: "u1", exp: Math.floor(Date.now() / 1000) + 7200 });
    fetchMock.mockReset();
    fetchMock
      .mockResolvedValueOnce({ ok: true, json: async () => ({ token: second }) })
      .mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
    await api("/today");
    const [, init] = fetchMock.mock.calls[1];
    expect(init.headers.Authorization).toBe(`Bearer ${second}`);
  });
});

describe("authHeaders — the trust-boundary seam", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    clearAuthToken();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  function respondWith(token: string) {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ token }) });
  }

  it("fetches the JWT from Better Auth's /api/auth/token with the session cookie", async () => {
    const token = fakeJwt({ sub: "u1", exp: Math.floor(Date.now() / 1000) + 3600 });
    respondWith(token);

    expect(await authHeaders()).toEqual({ Authorization: `Bearer ${token}` });

    const [url, init] = fetchMock.mock.calls[0];
    // The regression this whole ticket exists for: the endpoint must be the JWT endpoint, and
    // what we send must be a JWT — not `session.token`, Better Auth's opaque session id, which
    // the API's decode_claims can only ever reject.
    expect(String(url)).toContain("/api/auth/token");
    expect(init.credentials).toBe("include");
    expect(token.split(".")).toHaveLength(3);
  });

  it("sends no header at all when signed out — never a fabricated one", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 401, json: async () => ({}) });
    expect(await authHeaders()).toEqual({});
  });

  it("sends no header when the auth server is unreachable, and does not throw", async () => {
    fetchMock.mockRejectedValue(new Error("network down"));
    await expect(authHeaders()).resolves.toEqual({});
  });

  it("reuses the cached token instead of minting one per API call", async () => {
    respondWith(fakeJwt({ sub: "u1", exp: Math.floor(Date.now() / 1000) + 3600 }));
    await authHeaders();
    await authHeaders();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("refetches once the cached token is inside the expiry skew", async () => {
    vi.useFakeTimers();
    const exp = Math.floor(Date.now() / 1000) + 60;
    respondWith(fakeJwt({ sub: "u1", exp }));
    await authHeaders();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(60_000 - EXPIRY_SKEW_MS + 1_000);
    await authHeaders();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("never caches a token whose exp it cannot read (e.g. an opaque session id)", async () => {
    respondWith("an-opaque-session-id-not-a-jwt");
    await authHeaders();
    await authHeaders();
    // exp unreadable -> unusable -> refetched every time, rather than pinned forever.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("jwtExpiryMs / isTokenUsable — cache lifetime only, never verification", () => {
  it("reads exp out of a JWT payload as epoch ms", () => {
    expect(jwtExpiryMs(fakeJwt({ exp: 1_800_000_000 }))).toBe(1_800_000_000_000);
  });

  it("is 0 for anything it cannot parse", () => {
    expect(jwtExpiryMs("not-a-jwt")).toBe(0);
    expect(jwtExpiryMs("a.!!!notbase64!!!.c")).toBe(0);
    expect(jwtExpiryMs(fakeJwt({ sub: "u1" }))).toBe(0); // no exp claim
  });

  it("treats an unreadable expiry as unusable rather than valid forever", () => {
    expect(isTokenUsable({ token: "x", expiresAtMs: 0 }, 1_000)).toBe(false);
    expect(isTokenUsable(null, 1_000)).toBe(false);
  });

  it("stops using a token before it expires, not after", () => {
    const now = 1_000_000;
    expect(isTokenUsable({ token: "x", expiresAtMs: now + EXPIRY_SKEW_MS + 1 }, now)).toBe(true);
    expect(isTokenUsable({ token: "x", expiresAtMs: now + EXPIRY_SKEW_MS - 1 }, now)).toBe(false);
  });
});

describe("shouldSwitchOrganization — only a real change clears the cache", () => {
  it("is false when the target is already active", () => {
    expect(shouldSwitchOrganization("org_1", "org_1")).toBe(false);
  });

  it("is true for an actual switch, including from no active org", () => {
    expect(shouldSwitchOrganization("org_1", "org_2")).toBe(true);
    expect(shouldSwitchOrganization(null, "org_2")).toBe(true);
    expect(shouldSwitchOrganization(undefined, "org_2")).toBe(true);
  });
});

describe("switchOrganization — clears BOTH caches, or org A's figures show under org B", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    clearAuthToken();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("clears the query cache and re-mints the JWT on a real switch", async () => {
    const tokenA = fakeJwt({ sub: "u1", activeOrganizationId: "org_1", exp: Math.floor(Date.now() / 1000) + 3600 });
    const tokenB = fakeJwt({ sub: "u1", activeOrganizationId: "org_2", exp: Math.floor(Date.now() / 1000) + 3600 });

    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ token: tokenA }) });
    expect(await authHeaders()).toEqual({ Authorization: `Bearer ${tokenA}` });

    const cleared = vi.fn();
    // The org switch itself goes through better-auth's transport (reachable now that the client
    // late-binds fetch — see customFetchImpl in lib/auth.ts).
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ id: "org_2" }),
      text: async () => JSON.stringify({ id: "org_2" }),
    });
    await switchOrganization({ clear: cleared }, "org_1", "org_2");

    const switchCall = fetchMock.mock.calls.find((c) => String(c[0]).includes("set-active"));
    expect(switchCall).toBeDefined();
    expect(cleared).toHaveBeenCalledTimes(1);

    // The JWT carries activeOrganizationId, which the API turns into the RLS org GUC. If the old
    // token survived the switch, every query would still be scoped to org_1 under org_2's name.
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ token: tokenB }) });
    expect(await authHeaders()).toEqual({ Authorization: `Bearer ${tokenB}` });
  });

  it("does nothing when the target org is already active", async () => {
    const cleared = vi.fn();
    await switchOrganization({ clear: cleared }, "org_1", "org_1");
    expect(cleared).not.toHaveBeenCalled();
  });
});
