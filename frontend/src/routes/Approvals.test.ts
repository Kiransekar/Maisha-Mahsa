// The branches on the approval screen that can lose real money if they drift:
//   1. approvalStance   — can it ever print "all verified" over a figure Mahsa contradicted?
//   2. confirmOk        — can the commit button enable on text the server will reject (or worse,
//                         on text that isn't a deliberate confirmation at all)?
//   3. drift/exactInr   — can a REAL mismatch render as agreement? (the sub-rupee GST/TDS case)
//   4. booksFreshness   — can a ✓ survive on inputs we cannot confirm are current?

import { describe, expect, it } from "vitest";
import {
  approvalStance,
  ago,
  booksFreshness,
  confirmOk,
  drift,
  exactInr,
  PAYLOAD_MAX_AGE_MS,
  type Figure,
} from "./Approvals";
import type { FreshnessData, SourceFreshness } from "../components/ConnectionHealth";
import { effectiveState } from "../components/VerifiedNumber";
import { inr } from "../lib/money";

function fig(state: string, target = state): Figure {
  return {
    target,
    label: target,
    claimed_paise: 1_00_000_00,
    recomputed_paise: state === "honest_pending" ? null : 1_00_000_00,
    recomputed_values: null,
    state,
    note: null,
  };
}

describe("approvalStance — the tone can never overstate what Mahsa did", () => {
  it("reports verified only when every figure was recomputed and matched", () => {
    const s = approvalStance([fig("verified", "a"), fig("verified", "b")]);
    expect(s.tone).toBe("verified");
    expect(s.headline).toContain("recomputed");
  });

  it("never says verified when a single figure was contradicted by the recomputation", () => {
    // THE case: 9 good figures and one mismatch must not average out into a ✓.
    const figures = [...Array(9)].map((_, i) => fig("verified", `ok${i}`));
    figures.push(fig("unbacked", "bad"));
    const s = approvalStance(figures);
    expect(s.tone).toBe("unbacked");
    expect(s.headline).toContain("did NOT match");
  });

  it("never says verified when nothing was recomputable at all", () => {
    // Honest-empty ≠ verified: no claims means no proof, not implicit success.
    const s = approvalStance([]);
    expect(s.tone).toBe("honest_pending");
    expect(s.tone).not.toBe("verified");
  });

  it("counts the unbacked figures, not just flags them", () => {
    const s = approvalStance([fig("verified", "a"), fig("honest_pending", "b")]);
    expect(s.tone).toBe("honest_pending");
    expect(s.headline).toContain("1 of 2");
  });
});

describe("confirmOk — the typed-commit gate", () => {
  it("accepts the domain name, tolerating case and stray whitespace like the server does", () => {
    // Server: confirm_text.strip().lower() == domain.lower(). Diverging here would enable the
    // button on text the API then 400s — friction that reads as bureaucracy, not safety.
    expect(confirmOk("gst", "gst")).toBe(true);
    expect(confirmOk("  GST  ", "gst")).toBe(true);
  });

  it("rejects empty, partial and wrong text so there is no accidental commit path", () => {
    expect(confirmOk("", "gst")).toBe(false);
    expect(confirmOk(" ", "gst")).toBe(false);
    expect(confirmOk("gs", "gst")).toBe(false);
    expect(confirmOk("yes", "gst")).toBe(false);
    expect(confirmOk("payroll", "gst")).toBe(false);
  });
});

describe("exactInr — money renders to the paisa, never rounded", () => {
  it("keeps the paise component instead of rounding it away", () => {
    // The bug: inr() is Math.round(paise/100), so 40 paise became "₹0".
    expect(exactInr(40)).toBe("₹0.40");
    expect(exactInr(1)).toBe("₹0.01");
    expect(exactInr(99)).toBe("₹0.99");
  });

  it("never collapses a non-zero amount to zero rupees and zero paise", () => {
    for (const p of [1, 7, 40, 99, 100, 101, 12345678]) {
      expect(exactInr(p)).not.toBe("₹0.00");
    }
  });

  it("groups in lakh/crore and pads paise to two digits", () => {
    expect(exactInr(1_23_456_78)).toBe("₹1,23,456.78");
    expect(exactInr(500)).toBe("₹5.00");
    expect(exactInr(505)).toBe("₹5.05");
  });

  it("signs a negative without mangling the paise", () => {
    expect(exactInr(-40)).toBe("-₹0.40");
    expect(exactInr(-505)).toBe("-₹5.05");
  });
});

describe("drift — a real mismatch must never read as agreement", () => {
  it("reports nothing when Mahsa produced no number or produced the same one", () => {
    expect(drift(12345678, null)).toBeNull();
    expect(drift(12345678, 12345678)).toBeNull();
  });

  it("reports a single paisa of drift", () => {
    // Sub-rupee drift is the whole point of the product — the old code printed "differs by ₹0".
    const d = drift(12345678, 12345677);
    expect(d).not.toBeNull();
    expect(d?.diffPaise).toBe(1);
    expect(exactInr(d!.diffPaise)).toBe("₹0.01");
  });

  it("flags the case where the two figures round to the SAME rupee string", () => {
    // Real collisions, confirmed against inr() itself rather than assumed. A 1-paise and a
    // 99-paise gap can BOTH vanish into the same rupee string — the sub-rupee band is not safe.
    for (const [claimed, recomputed, diff] of [
      [12345678, 12345677, 1],
      [12345678, 12345690, 12],
      [12345650, 12345749, 99],
    ] as const) {
      expect(inr(claimed)).toBe(inr(recomputed)); // the rounded strings really do agree
      const d = drift(claimed, recomputed);
      expect(d?.diffPaise).toBe(diff);
      expect(d?.indistinguishable).toBe(true);
      // ...and rendered exactly, they are distinguishable again — which is the fix.
      expect(exactInr(claimed)).not.toBe(exactInr(recomputed));
    }
  });

  it("still reports exact sub-rupee drift when the rounded strings happen to differ", () => {
    // 12345678 vs 12345638 straddles the .5 boundary, so inr() DOES separate them — but the
    // difference is 40 paise and the old code rendered it as "differs by ₹0" regardless. The
    // exact-paise drift line is what makes that readable; `indistinguishable` is only about
    // whether the PAIR also needs restating.
    expect(inr(12345678)).not.toBe(inr(12345638));
    const d = drift(12345678, 12345638);
    expect(d?.diffPaise).toBe(40);
    expect(d?.indistinguishable).toBe(false);
    expect(exactInr(d!.diffPaise)).toBe("₹0.40");
    expect(inr(d!.diffPaise)).toBe("₹0"); // what it used to say
  });

  it("does not flag as indistinguishable when the rounded strings already differ", () => {
    const d = drift(10000, 20000); // ₹100 vs ₹200
    expect(d?.diffPaise).toBe(10000);
    expect(d?.indistinguishable).toBe(false);
  });

  it("is symmetric — drift is a magnitude, whichever side is larger", () => {
    expect(drift(12345678, 12345638)?.diffPaise).toBe(drift(12345638, 12345678)?.diffPaise);
  });
});

function source(over: Partial<SourceFreshness> = {}): SourceFreshness {
  return {
    key: "bank_feeds",
    label: "Bank feeds",
    last_updated: "2026-07-21",
    age_days: 0,
    threshold_days: 2,
    stale: false,
    synced: true,
    note: "",
    ...over,
  };
}

function health(over: Partial<FreshnessData["overall"]> = {}): FreshnessData {
  return {
    as_of: "2026-07-21",
    sources: [source(), source({ key: "gst_filings", label: "GST filings" })],
    overall: {
      status: "fresh",
      healthy: true,
      headline: "",
      worst_age_days: 0,
      never_synced: [],
      stale: [],
      ...over,
    },
  };
}

describe("booksFreshness — a ✓ only survives on inputs we can confirm are current", () => {
  it("is fresh when sources are current and the page was just loaded", () => {
    const f = booksFreshness(health(), 0);
    expect(f.stale).toBe(false);
    expect(f.why).toBeNull();
  });

  it("treats a MISSING health payload as unknown, never as all-clear and never as a false 'stale' claim", () => {
    // Invariant 1: unknown => not verified — but invariant 3 (never state a cause you don't know)
    // means the check-failed case must say "unknown", not "stale". One failed health request must
    // not silently restore ✓ on the screen where money gets committed, but it also must not tell
    // the user a fact ("stale") we cannot back.
    const f = booksFreshness(undefined, 0);
    expect(f.stale).toBe("unknown");
    expect(f.why).toBeTruthy();
  });

  it("is stale when a source has never synced, and names it", () => {
    const f = booksFreshness(health({ never_synced: ["gst_filings"] }), 0);
    expect(f.stale).toBe(true);
    expect(f.why).toContain("GST filings");
  });

  it("is stale when a source is past its freshness limit, and names it", () => {
    const f = booksFreshness(health({ stale: ["bank_feeds"] }), 0);
    expect(f.stale).toBe(true);
    expect(f.why).toContain("Bank feeds");
  });

  it("goes stale purely from the page sitting open past the limit", () => {
    // THE reported case: a tab left open rendering ✓ on hours-old figures.
    expect(booksFreshness(health(), PAYLOAD_MAX_AGE_MS - 1).stale).toBe(false);
    const f = booksFreshness(health(), PAYLOAD_MAX_AGE_MS + 1);
    expect(f.stale).toBe(true);
    expect(f.why).toContain("re-checked");
  });

  it("actually downgrades a verified chip — the wiring, not just the boolean", () => {
    // Guards the composition the screen relies on: if booksFreshness ever returned stale=false
    // for an unknown payload, this ✓ would survive and the whole fix would be decorative.
    // "unknown" must downgrade exactly as hard as a known `true` does — only the copy differs.
    const stale = booksFreshness(undefined, 0).stale;
    expect(stale).toBe("unknown");
    expect(effectiveState("verified", stale)).toBe("honest_pending");
    expect(effectiveState("verified", booksFreshness(health(), 0).stale)).toBe("verified");
  });

  it("never upgrades an unbacked figure, however fresh the inputs are", () => {
    expect(effectiveState("unbacked", booksFreshness(health(), 0).stale)).toBe("unbacked");
  });
});

describe("ago — page age is stated, never rounded down to 'just now'", () => {
  it("does not print '0 minutes' for a sub-minute age", () => {
    expect(ago(0)).toBe("less than a minute ago");
    expect(ago(59_000)).toBe("less than a minute ago");
  });

  it("counts minutes and then hours", () => {
    expect(ago(60_000)).toBe("1 minute ago");
    expect(ago(120_000)).toBe("2 minutes ago");
    expect(ago(3_600_000)).toBe("1 hour ago");
    expect(ago(7_200_000)).toBe("2 hours ago");
  });
});
