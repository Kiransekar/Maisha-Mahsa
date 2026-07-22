// The trust branch: what makes a figure show ✓, and what must never make it show ✓.
// Guards MMX-1.0 §0.4 (no ✓ Verified without recomputation) + UX research T4 (stale ✓ is a lie)
// on the client side, where a payload-shape change could silently re-introduce a fabricated ✓.

import { describe, expect, it } from "vitest";
import { effectiveState, type VerifyState } from "./VerifiedNumber";
import { inr, inrOrPending } from "../lib/money";

describe("effectiveState — staleness downgrades verification", () => {
  it("downgrades a verified figure to honest-pending when its inputs are stale", () => {
    // T4: a recomputation against stale data no longer stands. This is THE case that matters.
    expect(effectiveState("verified", true)).toBe("honest_pending");
  });

  it("keeps a verified figure verified when data is fresh", () => {
    expect(effectiveState("verified", false)).toBe("verified");
  });

  it("never upgrades anything to verified — staleness can only downgrade", () => {
    const states: VerifyState[] = ["honest_pending", "unbacked"];
    for (const s of states) {
      expect(effectiveState(s, false)).not.toBe("verified");
      expect(effectiveState(s, true)).not.toBe("verified");
    }
  });
});

describe("money rendering", () => {
  it("groups in lakh/crore, not thousands", () => {
    // ₹12,34,567 — the Indian convention. A western-grouped ₹1,234,567 is a defect.
    expect(inr(12_34_567_00)).toBe("₹12,34,567");
  });

  it("renders an unknown amount as a dash, never as ₹0", () => {
    // "We don't know" and "it is zero" are different facts. Conflating them invents a number.
    expect(inrOrPending(null)).toBe("—");
    expect(inrOrPending(undefined)).toBe("—");
    expect(inrOrPending(0)).toBe("₹0");
  });
});
