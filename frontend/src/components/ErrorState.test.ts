// The §0.4-critical branch for the PWA ticket (WS7.9): being offline must never let a figure
// keep reading ✓. There is no separate "offline" code path in the app — a real offline fetch()
// just rejects (a plain TypeError, no HTTP response), which is indistinguishable from any other
// unreachable-server failure, and the app's EXISTING error + staleness machinery already handles
// that. This test pins the two halves of that chain together:
//
//   1. classify() must route an offline-shaped failure (a non-ApiError) through the same
//      "api_down" bucket a down server gets — see public/sw.js's header comment for why this
//      file deliberately adds no new offline-specific signal instead of reusing this one.
//   2. Whatever a screen marks `stale` in response to that error, effectiveState() must
//      downgrade a "verified" figure to "honest_pending" — never leave it at ✓, never crash.

import { describe, expect, it } from "vitest";
import { classify } from "./ErrorState";
import { ApiError } from "../lib/api";
import { effectiveState } from "./VerifiedNumber";

describe("classify — offline and down-server failures read the same way", () => {
  it("classifies a raw network failure (what navigator offline actually throws) as api_down", () => {
    // fetch() while offline rejects with a TypeError, never an ApiError — there was no response.
    expect(classify(new TypeError("Failed to fetch"))).toBe("api_down");
  });

  it("classifies a 5xx ApiError (server down) the same way as an offline failure", () => {
    expect(classify(new ApiError(503, "503 Service Unavailable"))).toBe("api_down");
  });

  it("does not conflate a real 4xx (e.g. bad auth) with an offline/down-server failure", () => {
    expect(classify(new ApiError(404, "404 Not Found"))).toBe("unknown");
  });
});

describe("offline failure -> stale -> downgrade, end to end", () => {
  it("a screen that marks last-known data stale on ANY classify()==api_down error downgrades ✓", () => {
    const offline = new TypeError("Failed to fetch");
    const serverDown = new ApiError(503, "503 Service Unavailable");

    for (const error of [offline, serverDown]) {
      expect(classify(error)).toBe("api_down");
      // This is exactly what Today.tsx / ConnectionHealth.tsx do: on error, render last-known
      // data with `stale` forced true. The rule that matters is effectiveState's, not a new one.
      expect(effectiveState("verified", true)).toBe("honest_pending");
    }
  });

  it("never upgrades a non-verified figure just because the network came back", () => {
    // Staleness clearing (stale=false) must not manufacture a ✓ out of ◐/✕ — only the server
    // payload's own state can do that. Guards against effectiveState growing an upgrade path.
    expect(effectiveState("honest_pending", false)).toBe("honest_pending");
    expect(effectiveState("unbacked", false)).toBe("unbacked");
  });
});
