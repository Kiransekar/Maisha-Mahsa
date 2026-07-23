// The trust branch: what makes a figure show ✓, and what must never make it show ✓.
// Guards MMX-1.0 §0.4 (no ✓ Verified without recomputation) + UX research T4 (stale ✓ is a lie)
// on the client side, where a payload-shape change could silently re-introduce a fabricated ✓.

import { describe, expect, it } from "vitest";
import {
  effectiveState,
  hasBrokenCitation,
  type VerifyState,
  type Working,
} from "./VerifiedNumber";
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

// ── SPEC-MEMCITE-1.0 §B2: a BROKEN citation downgrades the badge, never silently ─────────
describe("effectiveState — a broken citation anchor downgrades verification", () => {
  it("downgrades a verified figure when a citation behind it is broken", () => {
    // §B2: a ✓ standing on a source row that no longer resolves is a claim we cannot make.
    expect(effectiveState("verified", false, true)).toBe("honest_pending");
  });

  it("keeps a verified figure verified when citations resolve (or moved — moved resolves)", () => {
    expect(effectiveState("verified", false, false)).toBe("verified");
  });

  it("never upgrades via the broken flag either", () => {
    expect(effectiveState("honest_pending", false, true)).toBe("honest_pending");
    expect(effectiveState("unbacked", false, true)).toBe("unbacked");
  });
});

describe("hasBrokenCitation — the exact resolution grammar", () => {
  const w = (resolution?: "resolved" | "moved" | "broken"): Working => ({
    documents: [{ label: "x.csv, row 2: …", resolution }],
  });

  it("true only for an explicit broken resolution", () => {
    expect(hasBrokenCitation(w("broken"))).toBe(true);
    expect(hasBrokenCitation(w("resolved"))).toBe(false);
    // MOVED resolves (with a visible note) — it must NOT downgrade the badge (§B2).
    expect(hasBrokenCitation(w("moved"))).toBe(false);
    // A coarse file-level ref makes no row claim — nothing to break (§B5).
    expect(hasBrokenCitation(w(undefined))).toBe(false);
    expect(hasBrokenCitation({ documents: [] })).toBe(false);
    expect(hasBrokenCitation(undefined)).toBe(false);
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
import { isRestricted, LockChip, VerifiedNumber } from "./VerifiedNumber";

// ── §B2 badge-downgrade UI: the full component, really rendered ──────────────────────────
describe("VerifiedNumber — citation resolution states in the working panel", () => {
  const base = { label: "Cash on hand", value: "₹1,20,000", asOf: "2026-07-23" };

  it("BROKEN: downgrades ✓ to ◐, says why, and states the broken citation", () => {
    const html = renderToStaticMarkup(
      createElement(VerifiedNumber, {
        ...base,
        state: "verified",
        working: {
          documents: [
            {
              label: "HDFC-May.csv, row 47: NEFT-000123 ₹1,20,000 Dr",
              resolution: "broken",
              note: "no row in the stored source file matches this citation's content hash (occurrence 1)",
            },
          ],
        },
      }),
    );
    expect(html).not.toContain("✓ recomputed"); // the fabricated-✓ this ticket exists to kill
    expect(html).toContain("◐");
    expect(html).toContain("Downgraded from ✓: a source citation behind this figure is broken");
    expect(html).toContain("citation broken");
    expect(html).toContain("content hash (occurrence 1)");
  });

  it("MOVED: keeps the ✓ but renders the visible moved note — never silently", () => {
    const html = renderToStaticMarkup(
      createElement(VerifiedNumber, {
        ...base,
        state: "verified",
        working: {
          documents: [
            {
              label: "HDFC-May.csv, row 47: NEFT-000123 ₹1,20,000 Dr",
              resolution: "moved",
              note: "row moved from 47 to 52",
            },
          ],
        },
      }),
    );
    expect(html).toContain("✓ recomputed"); // MOVED resolves — the row's content still stands
    expect(html).toContain("row moved from 47 to 52");
    expect(html).not.toContain("citation broken");
  });

  it("RESOLVED: a clean anchor renders its excerpt with no warning text", () => {
    const html = renderToStaticMarkup(
      createElement(VerifiedNumber, {
        ...base,
        state: "verified",
        working: {
          documents: [{ label: "HDFC-May.csv, row 47: NEFT ₹1,20,000 Dr", resolution: "resolved" }],
        },
      }),
    );
    expect(html).toContain("HDFC-May.csv, row 47");
    expect(html).not.toContain("row moved");
    expect(html).not.toContain("citation broken");
    expect(html).not.toContain("Downgraded");
  });
});

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
