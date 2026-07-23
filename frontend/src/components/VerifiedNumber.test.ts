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

// ── T11 field-level RBAC: the lock chip and its guard ────────────────────────
// The server strips a sensitive value and sends {restricted: true, reason} instead
// (app/core/landing.mask_field). The chip must make that VISIBLE — a blank or missing cell
// is the hidden-not-absent failure the WS7 contract forbids. renderToStaticMarkup is a real
// React render with no jsdom (same pattern as BankCsvImport.test.tsx; no new dependency).

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { isRestricted, LockChip } from "./VerifiedNumber";

describe("LockChip — a restricted field is stated, with its reason, never blank", () => {
  it("renders 'restricted' and the server's reason verbatim", () => {
    const html = renderToStaticMarkup(
      createElement(LockChip, { reason: "requires salary_detail clearance" }),
    );
    expect(html).toContain("restricted");
    expect(html).toContain("requires salary_detail clearance");
  });

  it("never renders a ₹ or a verification glyph — a lock is not a badge state", () => {
    // Kills: routing a restricted field through VerifiedNumber (which would show ✕/◐ and an
    // amount slot) instead of the lock chip.
    const html = renderToStaticMarkup(createElement(LockChip, { reason: "r" }));
    expect(html).not.toContain("₹");
    expect(html).not.toContain("✓");
    expect(html).not.toContain("◐");
    expect(html).not.toContain("✕");
  });
});

describe("isRestricted — guards the exact server shape, nothing else", () => {
  it("accepts only restricted === true objects", () => {
    expect(isRestricted({ restricted: true, reason: "x" })).toBe(true);
    expect(isRestricted({ restricted: false, reason: "x" })).toBe(false);
    expect(isRestricted({ restricted: "true", reason: "x" })).toBe(false);
    expect(isRestricted(1234567)).toBe(false);
    expect(isRestricted(null)).toBe(false);
    expect(isRestricted(undefined)).toBe(false);
  });
});
