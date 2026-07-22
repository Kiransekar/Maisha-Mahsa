// The one branch in WS7.7 that can put a fabricated ✓ on screen: whether a source counts as
// stale. Everything downstream (effectiveState → the ◐ downgrade) is already tested; this pins
// the input that drives it, including the two cases that fail OPEN if written naively —
// a never-synced source, and a missing/failed freshness payload.

import { describe, expect, it } from "vitest";
import {
  isSourceStale,
  sourceState,
  stateForSource,
  type FreshnessData,
  type SourceFreshness,
} from "./ConnectionHealth";

function source(over: Partial<SourceFreshness> & { key: string }): SourceFreshness {
  return {
    label: "Bank feeds",
    last_updated: "2026-07-20",
    age_days: 1,
    threshold_days: 2,
    stale: false,
    synced: true,
    note: "",
    ...over,
  };
}

const data = (sources: SourceFreshness[]): FreshnessData => ({
  as_of: "2026-07-21",
  sources,
  overall: {
    status: "fresh",
    healthy: true,
    headline: "",
    worst_age_days: 1,
    never_synced: [],
    stale: [],
  },
});

describe("isSourceStale — the server decides, and unknown never reads as fresh", () => {
  it("reports a fresh source as not stale", () => {
    expect(isSourceStale(data([source({ key: "bank_feeds" })]), "bank_feeds")).toBe(false);
  });

  it("reports a stale source as stale", () => {
    const d = data([source({ key: "bank_feeds", stale: true, age_days: 9 })]);
    expect(isSourceStale(d, "bank_feeds")).toBe(true);
  });

  it("treats a never-synced source as stale, not as healthy", () => {
    // freshness.py sends synced=false with last_updated=null and stale=true. If this ever read
    // false, a figure built on a source with NO DATA AT ALL would keep its ✓.
    const d = data([
      source({ key: "payroll", synced: false, stale: true, last_updated: null, age_days: null }),
    ]);
    expect(isSourceStale(d, "payroll")).toBe(true);
  });

  it("treats a missing payload as stale — an unconfirmed ✓ is not a ✓", () => {
    // THE fail-open case: the health request failed. We cannot confirm freshness, so we must not
    // let every screen quietly restore ✓.
    expect(isSourceStale(undefined, "bank_feeds")).toBe(true);
  });

  it("treats an unknown source key as stale", () => {
    expect(isSourceStale(data([source({ key: "bank_feeds" })]), "gst_filings")).toBe(true);
  });
});

describe("sourceState — 'we checked and it is old' is not 'we could not check'", () => {
  // isSourceStale collapses both into `true` so the BADGE fails closed. That collapse must not
  // reach the copy: telling the user their inputs are stale when the truth is that the health
  // check never came back asserts a cause the client cannot know (invariant 3).
  it("reports a checked, in-threshold source as fresh", () => {
    expect(sourceState(data([source({ key: "bank_feeds" })]), "bank_feeds")).toBe("fresh");
  });

  it("reports a checked, past-threshold source as stale", () => {
    const d = data([source({ key: "bank_feeds", stale: true, age_days: 9 })]);
    expect(sourceState(d, "bank_feeds")).toBe("stale");
  });

  it("reports a never-synced source as stale, not fresh", () => {
    const d = data([
      source({ key: "payroll", synced: false, stale: true, last_updated: null, age_days: null }),
    ]);
    expect(sourceState(d, "payroll")).toBe("stale");
  });

  it("reports a missing payload as unknown — NOT stale", () => {
    expect(sourceState(undefined, "bank_feeds")).toBe("unknown");
  });

  it("reports an absent key as unknown — NOT stale", () => {
    expect(sourceState(data([source({ key: "bank_feeds" })]), "gst_filings")).toBe("unknown");
  });
});

describe("stateForSource — the freshness-driven downgrade", () => {
  it("downgrades a verified figure to honest-pending on a stale source", () => {
    const d = data([source({ key: "bank_feeds", stale: true, age_days: 9 })]);
    expect(stateForSource("verified", d, "bank_feeds")).toBe("honest_pending");
  });

  it("keeps a verified figure verified on a current source", () => {
    expect(stateForSource("verified", data([source({ key: "bank_feeds" })]), "bank_feeds")).toBe(
      "verified",
    );
  });

  it("never upgrades an unbacked figure, fresh source or not", () => {
    const d = data([source({ key: "bank_feeds" })]);
    expect(stateForSource("unbacked", d, "bank_feeds")).toBe("unbacked");
    expect(stateForSource("unbacked", undefined, "bank_feeds")).toBe("unbacked");
  });
});
