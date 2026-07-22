// The three pure branches shared by both hub altitudes. Each one is a place a ✓ could be
// fabricated or a deadline could be misread, which is the only reason they are functions.

import { describe, expect, it } from "vitest";
import { coverageText, deadlineWhen, honestState, type Deadline } from "./Domain";
import { kpiValue, runwayText } from "./Domains";

describe("honestState — a ✓ can only come from a live, recognised server state", () => {
  it("passes the three known states straight through while Mahsa is up", () => {
    expect(honestState("verified", true)).toBe("verified");
    expect(honestState("honest_pending", true)).toBe("honest_pending");
    expect(honestState("unbacked", true)).toBe("unbacked");
  });

  it("downgrades verified to ◐ when Mahsa is unreachable", () => {
    // THE case: /api/domains/{d} derives `state` from the static recompute-coverage table, so it
    // still says "verified" during an outage. Invariant 6 — nothing reads ✓ with the gate down.
    expect(honestState("verified", false)).toBe("honest_pending");
  });

  it("never promotes an unknown, empty or missing state to verified", () => {
    for (const bad of ["", "VERIFIED", "ok", "pending", "true", null, undefined]) {
      expect(honestState(bad, true)).toBe("unbacked");
    }
  });

  it("leaves an already-failing figure failing during an outage", () => {
    // A downgrade must never accidentally soften ✕ into ◐.
    expect(honestState("unbacked", false)).toBe("unbacked");
  });
});

describe("coverageText — honest-empty is not zero", () => {
  it("states that a domain has no figures rather than reporting 0 of 0", () => {
    expect(coverageText(0, 0, true)).toBe("no figures published on this domain yet");
  });

  it("claims nothing verified while Mahsa is down, whatever the server counted", () => {
    // The server's `coverage.verified` is computed from the same outage-blind table, so a
    // non-zero count arrives during an outage. It must not be restated as recomputed.
    expect(coverageText(7, 9, false)).not.toContain("recomputed");
    expect(coverageText(7, 9, false)).toContain("none verified");
  });

  it("reports the real fraction when the gate is up", () => {
    expect(coverageText(0, 9, true)).toBe("0 of 9 figures recomputed");
    expect(coverageText(9, 9, true)).toBe("9 of 9 figures recomputed");
  });
});

describe("runwayText — an ambiguous null is never resolved in our favour", () => {
  it("says the ledger is empty rather than claiming an unbounded runway", () => {
    // THE case: a brand-new user, zero accounts. net_burn == 0 because nothing exists, so the
    // server sends runway_months = null. "not burning — unbounded" would be a flattering lie.
    const t = runwayText({ runway_months: null, accounts: 0 });
    expect(t).toBe("no ledger yet — no runway to compute");
    expect(t).not.toContain("unbounded");
    expect(t).not.toContain("not burning");
  });

  it("refuses to claim 'not burning' from a null it cannot attribute", () => {
    // Accounts exist, but the payload carries no burn/revenue split — revenue >= burn and
    // no-transactions-this-window are indistinguishable here, so neither is asserted.
    const t = runwayText({ runway_months: null, accounts: 3 });
    expect(t).toBe("not yet known — we don't guess");
    expect(t).not.toContain("unbounded");
  });

  it("reports a real runway, including a fractional one", () => {
    expect(runwayText({ runway_months: 7.25, accounts: 2 })).toBe("7.25 mo");
    expect(runwayText({ runway_months: 0, accounts: 2 })).toBe("0 mo");
  });
});

describe("kpiValue — an empty source is not a ₹0 position", () => {
  it("returns null (say it is unwired) for a zero read with no account wired", () => {
    expect(kpiValue(0, 0)).toBeNull();
  });

  it("renders a genuine zero once accounts exist", () => {
    // Zero cash across two real accounts IS a measured fact and must not be hidden.
    expect(kpiValue(0, 2)).toBe("₹0");
  });

  it("always renders a non-zero figure, even with no bank account (AR/AP come from invoices)", () => {
    expect(kpiValue(1_23_45_600, 0)).toBe("₹1,23,456");
    expect(kpiValue(-50_00, 0)).toBe("-₹50");
  });

  it("groups in lakh/crore, not thousands", () => {
    expect(kpiValue(1_00_00_000_00, 1)).toBe("₹1,00,00,000");
  });
});

describe("deadlineWhen — the 'when' half of the alert grammar", () => {
  const base: Deadline = { domain: "gst", form_name: "GSTR-3B", due_date: "2026-07-20", label: "T-7" };

  it("says overdue, by how much, and what the date was", () => {
    const w = deadlineWhen({ ...base, label: "OVERDUE", days_overdue: 3 });
    expect(w.overdue).toBe(true);
    expect(w.text).toBe("overdue by 3 days — was due 2026-07-20");
  });

  it("singularises one day on both branches", () => {
    expect(deadlineWhen({ ...base, label: "OVERDUE", days_overdue: 1 }).text).toContain("1 day —");
    expect(deadlineWhen({ ...base, days_to_due: 1 }).text).toContain("in 1 day —");
  });

  it("distinguishes due-today from a missing day count", () => {
    // 0 is a real "today"; absent is not — assuming 0 would invent an urgency we weren't told.
    expect(deadlineWhen({ ...base, days_to_due: 0 }).text).toBe("due today — 2026-07-20");
    expect(deadlineWhen(base).text).toBe("due 2026-07-20");
    expect(deadlineWhen(base).overdue).toBe(false);
  });

  it("still reports overdue when the server omitted the day count", () => {
    const w = deadlineWhen({ ...base, label: "OVERDUE" });
    expect(w.overdue).toBe(true);
    expect(w.text).toBe("overdue — was due 2026-07-20");
  });
});
