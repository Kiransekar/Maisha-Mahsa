// The load-bearing branches on the filing screen. Each block names the mutation it kills:
//   1. badgeState        — `return s as VerifyState` (a hostile/typo'd server state renders ✓)
//   2. amountText        — `paise ?? 0` (an unknown fee prints ₹0: the invented-₹ failure)
//   3. confirmDisabledReason — `return null` / reordered checks (Accountant's Record enables,
//                          or the capability reason is masked by the typed-gate message)
//   4. rupeesToPaise     — `* 1` or accepting decimals (a paisa-wrong statutory figure)
//   5. buildPreviewRequest — dropping the invalid guard (a null amount silently becomes NaN)
// The typed-confirm gate itself is `confirmOk`, already regression-locked in Approvals.test.ts;
// here we only assert the flow uses it through confirmDisabledReason.

import { describe, expect, it } from "vitest";
import {
  amountText,
  badgeState,
  buildPreviewRequest,
  confirmDisabledReason,
  rupeesToPaise,
  type QueueItem,
} from "./Filings";
import { confirmOk } from "./Approvals";
import { inr } from "../lib/money";

describe("badgeState — badge honesty: only the server's three states exist", () => {
  it("passes the three known states through unchanged", () => {
    expect(badgeState("verified")).toBe("verified");
    expect(badgeState("honest_pending")).toBe("honest_pending");
    expect(badgeState("unbacked")).toBe("unbacked");
  });

  it("falls anything unknown to unbacked — NEVER to verified", () => {
    // Kills: `return s as VerifyState`. A server bug (or tampered payload) claiming a state we
    // don't recognise must read as ✕, because an optimistic ✓ is a fabricated verification.
    for (const s of ["Verified", "ok", "", "sealed", "green"]) {
      expect(badgeState(s)).toBe("unbacked");
    }
  });
});

describe("amountText — a null amount is unknown, never ₹0", () => {
  it("renders the honest sentence for null", () => {
    // Kills: `paise ?? 0`. T12/invariant 2 — an unported fee must not print an invented ₹0.
    expect(amountText(null)).toBe("not yet known — we don't guess");
    expect(amountText(null)).not.toContain("₹");
  });

  it("renders real amounts through the one lakh/crore renderer", () => {
    expect(amountText(12_34_567_00)).toBe(inr(12_34_567_00));
    expect(amountText(0)).toBe(inr(0)); // a GENUINE zero is a zero, not "unknown"
  });
});

describe("confirmDisabledReason — the disabled Record button says why", () => {
  const CAP_REASON = "statutory filing: requires Owner or Admin regardless of matrix_config";

  it("capability denial wins, and carries the server's own reason", () => {
    // Kills: `return null` (Accountant's button enables) and swapped precedence (the role
    // reason drowned by 'type to confirm', hiding WHY from the Accountant).
    const r = confirmDisabledReason(false, CAP_REASON, true);
    expect(r).toContain(CAP_REASON);
    expect(r).toContain("Owner/Admin");
  });

  it("falls back to honest copy when the server sent no reason", () => {
    expect(confirmDisabledReason(false, null, true)).toContain("cannot record a statutory filing");
  });

  it("typed gate blocks an allowed role until the phrase matches", () => {
    expect(confirmDisabledReason(true, null, false)).toContain("typed confirmation");
    expect(confirmDisabledReason(true, null, true)).toBeNull();
  });

  it("is fed by the same confirmOk gate the Approvals commit uses", () => {
    expect(confirmOk(" gstr-3b ", "GSTR-3B")).toBe(true);
    expect(confirmOk("gstr3b", "GSTR-3B")).toBe(false);
    expect(confirmDisabledReason(true, null, confirmOk("gstr3b", "GSTR-3B"))).not.toBeNull();
  });
});

describe("rupeesToPaise — statutory figures are exact integer paise", () => {
  it("converts whole rupees exactly", () => {
    // Kills: `* 1` (paise-vs-rupee unit bug — a 100x wrong filing figure).
    expect(rupeesToPaise("1234")).toBe(123400);
    expect(rupeesToPaise(" 0 ")).toBe(0);
  });

  it("refuses anything that is not a whole-rupee integer", () => {
    // Kills: parseFloat leniency. "12.50", "1e3" or "" must disable preview, not guess.
    for (const bad of ["12.5", "-5", "1e3", "", "₹100", "1,000"]) {
      expect(rupeesToPaise(bad)).toBeNull();
    }
  });
});

describe("buildPreviewRequest — an invalid amount never reaches the wire", () => {
  const item: QueueItem = {
    id: 7,
    domain: "gst",
    form_name: "GSTR-3B (2026-07)",
    filing_period: "2026-07",
    due_date: "2026-08-20",
    status: "pending",
    days_overdue: 3,
    due_in_days: 0,
    kind: "gstr3b",
  };
  const base = {
    filing_period: "2026-07",
    due_date: "2026-08-20",
    filed_date: "2026-08-23",
    is_nil: "",
    out_igst: "100000",
    out_cgst: "0",
    out_sgst: "0",
    itc_igst: "40000",
    itc_cgst: "0",
    itc_sgst: "0",
    return_type: "",
    quarter: "",
    acknowledgement: "",
    total_deducted: "0",
  };

  it("builds exact-paise bodies for valid input", () => {
    const { body, invalid, path } = buildPreviewRequest(item, base);
    expect(invalid).toBeNull();
    expect(path).toBe("/filings/gstr3b/preview");
    const b = body as { output: Record<string, number>; itc_available: Record<string, number> };
    expect(b.output.igst).toBe(100000 * 100);
    expect(b.itc_available.igst).toBe(40000 * 100);
  });

  it("returns an invalid reason instead of a body when an amount is malformed", () => {
    // Kills: dropping the null-guard, which would send NaN paise to a statutory preview.
    const { body, invalid } = buildPreviewRequest(item, { ...base, out_igst: "1,00,000" });
    expect(invalid).not.toBeNull();
    expect(body).toBeNull();
  });
});
