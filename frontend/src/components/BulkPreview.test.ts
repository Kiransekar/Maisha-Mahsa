// The two branches in the bulk flow that can lose money or lose a row silently.
//
//   impactSummary   — invariant 2: an unknown ₹ must never render as ₹0. This is the number the
//                     user reads immediately before authorising a multi-row write.
//   bulkBlockReason — anti-pattern #3 / T3: a row that cannot be bulk-actioned must say WHY.
//                     If this ever returned null for a Mahsa-blocked figure, the UI would offer
//                     a checkbox that bulk-waves through a figure Mahsa refused to back.

import { describe, expect, it } from "vitest";
import {
  bulkBlockReason,
  confirmPlan,
  impactSummary,
  type BulkPreviewData,
  type BulkRow,
} from "./BulkPreview";

const row = (id: string): BulkRow => ({
  id,
  domain: "gst",
  what: `row ${id}`,
  impact_paise: 100,
  will: "approved",
});

const previewOf = (over: Partial<BulkPreviewData> = {}): BulkPreviewData => ({
  mahsa_up: true,
  action: "approve",
  rows: [row("a"), row("b")],
  skipped: [],
  total_impact_paise: 200,
  unquantified_rows: 0,
  committed: false,
  committed_count: 0,
  ...over,
});

describe("confirmPlan — the confirm commits exactly what was previewed", () => {
  it("sends the SERVER's previewed row ids, not whatever is selected now", () => {
    // THE case this ticket exists for: the user previewed a and b, then ticked c. The confirm
    // must carry [a, b]. If this ever returned the live selection, c would be committed without
    // ever having been shown — a silent bulk write.
    expect(confirmPlan(previewOf())).toEqual({ action: "approve", ids: ["a", "b"] });
  });

  it("carries the server's own verb, never defaulting an absent one to approve", () => {
    expect(confirmPlan(previewOf({ action: "reject" }))?.action).toBe("reject");
    // action:null used to become "approve" — an unknown mutation resolving towards moving money.
    expect(confirmPlan(previewOf({ action: null }))).toBeNull();
  });

  it("offers no confirm when Mahsa is down, nothing is eligible, or it already committed", () => {
    expect(confirmPlan(previewOf({ mahsa_up: false }))).toBeNull();
    expect(confirmPlan(previewOf({ rows: [] }))).toBeNull();
    // Re-confirming a committed panel would double-apply every sealed row.
    expect(confirmPlan(previewOf({ committed: true, committed_count: 2 }))).toBeNull();
  });

  it("ignores skipped rows — they were shown as NOT changing", () => {
    const p = previewOf({ skipped: [{ ...row("z"), reason: "wrong queue" }] });
    expect(confirmPlan(p)?.ids).toEqual(["a", "b"]);
  });
});

describe("impactSummary — never invents a rupee value", () => {
  it("says the total is not known rather than showing ₹0", () => {
    // THE case: every eligible row has an unknown impact. A confident "₹0" here would be a
    // fabricated number authorising a real write.
    const s = impactSummary({ total_impact_paise: null, unquantified_rows: 3 });
    expect(s).toContain("not yet known");
    expect(s).not.toContain("₹0");
    expect(s).toContain("3 row(s)");
  });

  it("reports a genuine zero as zero", () => {
    // Honest-empty ≠ zero, and the converse: a real ₹0 must not be disguised as unknown.
    const s = impactSummary({ total_impact_paise: 0, unquantified_rows: 0 });
    expect(s).toContain("₹0");
    expect(s).not.toContain("not yet known");
  });

  it("groups the total in lakh/crore and flags rows excluded from it", () => {
    const s = impactSummary({ total_impact_paise: 12_34_567_00, unquantified_rows: 2 });
    expect(s).toContain("₹12,34,567");
    // The caveat matters: a total that silently omits 2 unknown rows reads as complete.
    expect(s).toContain("2 row(s)");
    expect(s).toContain("not counted above");
  });
});

describe("bulkBlockReason — a non-selectable row states why", () => {
  it("refuses a Mahsa-blocked figure even if the payload marks it selectable", () => {
    // Defence in depth: selectable=true + mahsa_blocked must still not get a checkbox.
    const r = bulkBlockReason({ selectable: true, queue: "mahsa_blocked" });
    expect(r).toContain("must be corrected");
  });

  it("allows only a selectable item awaiting sign-off", () => {
    expect(bulkBlockReason({ selectable: true, queue: "awaiting_approval" })).toBeNull();
  });

  it("gives a specific reason, never a bare 'not eligible', for the wrong queue", () => {
    const r = bulkBlockReason({ selectable: true, queue: "needs_document" });
    expect(r).toContain("needs_document");
    expect(r).toContain("awaiting sign-off");
  });

  it("blocks an item the server marked non-selectable", () => {
    expect(bulkBlockReason({ selectable: false, queue: "awaiting_approval" })).not.toBeNull();
  });
});
