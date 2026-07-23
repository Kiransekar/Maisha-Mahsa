// MEM.P0-5 root-cause fix: `api()` used to throw an ApiError carrying only
// "{status} {statusText}", losing the server's own message body — so no caller could ever
// render a verbatim server error (needed for the memory-overflow 422, whose text is dynamic:
// the exact char count). Fixed once here, at the single seam every call routes through.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Stub the auth seam directly (auth.test.ts precedent) rather than let getAuthToken's OWN
// fetch(/api/auth/token) collide with the fetchMock below — this test is about api()'s error
// handling, not the auth handshake.
vi.mock("./auth", () => ({
  authHeaders: async () => ({}),
  clearAuthToken: () => {},
}));

import { api, ApiError } from "./api";

describe("api() — ApiError.detail carries the server's own {detail} body", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("a JSON {detail} body on a non-ok response is captured verbatim", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 422,
      statusText: "Unprocessable Entity",
      json: async () => ({ detail: "CFO memory is 2301 chars after consolidation; the limit is 2200." }),
    });
    await expect(api("/memory", { method: "PUT", body: "{}" })).rejects.toMatchObject({
      status: 422,
      detail: "CFO memory is 2301 chars after consolidation; the limit is 2200.",
    });
  });

  it("a non-JSON or detail-less body leaves detail undefined, never a crash", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: async () => {
        throw new Error("not json");
      },
    });
    const err = await api("/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).detail).toBeUndefined();
    expect((err as ApiError).status).toBe(500);
  });
});
