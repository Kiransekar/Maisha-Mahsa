// The load-bearing branches on the payroll-run screen. Each block names the mutation it kills:
//   1. figureProps            — `f.state as VerifyState` (a hostile/typo'd server state renders
//                               ✓) and `value_paise ?? 0` (an unknown amount prints ₹0);
//                               dropping the T4 staleness downgrade (stale ✓ stays ✓).
//   2. runConfirmDisabledReason — removing the no-preview gate (Confirm enables sight-unseen —
//                               the INVARIANT 9 regression), or masking the capability reason.
//   3. defaultMonth           — off-by-one on getMonth() (previews January as "2026-00").
// The typed-confirm gate itself is `confirmOk` (regression-locked in Approvals.test.ts) and the
// badge whitelist is `badgeState` (locked in Filings.test.ts); here we lock how THIS screen
// composes them.

import { describe, expect, it } from "vitest";
import { defaultMonth, figureProps, runConfirmDisabledReason } from "./PayrollRun";
import type { ServerFigure } from "./Filings";
import { inr } from "../lib/money";

function fig(over: Partial<ServerFigure> = {}): ServerFigure {
  return {
    target: "emp1.pf_employee",
    label: "PF (employee)",
    value_paise: 1_800_00,
    state: "verified",
    working: { inputs: [], formula: null, citations: [], documents: [], verdict_hash: null, note: null },
    ...over,
  };
}

describe("figureProps — badged per-employee figures render from the payload only", () => {
  it("renders a verified server figure as ✓ with the lakh/crore amount", () => {
    const p = figureProps(fig(), false);
    expect(p.state).toBe("verified");
    expect(p.value).toBe(inr(1_800_00));
    expect(p.label).toBe("PF (employee)");
  });

  it("falls an unknown server state to unbacked — NEVER to verified", () => {
    // Kills: `f.state as VerifyState`. A tampered payload claiming "ok"/"green" must read ✕.
    for (const s of ["Verified", "ok", "green", ""]) {
      expect(figureProps(fig({ state: s }), false).state).toBe("unbacked");
    }
  });

  it("renders a null amount as the honest sentence, never ₹0", () => {
    // Kills: `value_paise ?? 0` — the invented-₹ failure (BUILD_CONTRACT invariant 2).
    const p = figureProps(fig({ value_paise: null }), false);
    expect(p.value).toBe("not yet known — we don't guess");
    expect(p.value).not.toContain("₹");
  });

  it("downgrades a stale ✓ to ◐ (T4), leaving ✕ alone", () => {
    // Kills: dropping `effectiveState` — a preview left open forever would keep its ✓.
    expect(figureProps(fig(), true).state).toBe("honest_pending");
    expect(figureProps(fig({ state: "unbacked" }), true).state).toBe("unbacked");
  });

  it("carries the server's note through (why a figure is ◐)", () => {
    const p = figureProps(
      fig({ working: { note: "TDS is not yet ported to Mahsa" } as ServerFigure["working"] }),
      false,
    );
    expect(p.note).toContain("not yet ported");
  });
});

describe("runConfirmDisabledReason — confirm is disabled until a preview exists", () => {
  it("without a preview the button is disabled regardless of everything else", () => {
    // Kills: removing the hasPreview gate — a confirm with no previewed figures is the exact
    // silent-bulk-mutation INVARIANT 9 forbids.
    const r = runConfirmDisabledReason(false, true, null, true);
    expect(r).toContain("Preview the run first");
  });

  it("with a preview, the capability denial wins and carries the server's reason", () => {
    const r = runConfirmDisabledReason(true, false, "missing capability: write", true);
    expect(r).toContain("missing capability: write");
  });

  it("with a preview and capability, the typed gate holds until the phrase matches", () => {
    expect(runConfirmDisabledReason(true, true, null, false)).toContain("typed confirmation");
    expect(runConfirmDisabledReason(true, true, null, true)).toBeNull();
  });
});

describe("defaultMonth — YYYY-MM of the given date", () => {
  it("pads the month and does not off-by-one", () => {
    // Kills: `getMonth()` without +1 (January -> "2026-00").
    expect(defaultMonth(new Date(2026, 0, 15))).toBe("2026-01");
    expect(defaultMonth(new Date(2026, 11, 31))).toBe("2026-12");
  });
});
