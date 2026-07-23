// P2-2 — the honesty gates of the GST detail panel, asserted directly.
//
// Repo convention (see Statements.test.tsx): no jsdom/@testing-library — pure functions plus
// renderToStaticMarkup for a REAL React render of the presentational pieces.

import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  DownloadsPanel,
  ImsPanel,
  ObligationsPanel,
  ReconPanel,
  imsConfirmPlan,
  obligationWhen,
  type GstDetailData,
  type GstFigure,
  type ImsPreview,
} from "./GstDetail";
import type { VerifyState } from "../components/VerifiedNumber";

const DRAFT_LABEL = "DRAFT — not IRP-registered; not a valid e-invoice until registered";

// The badge gate every figure passes through in these tests: fail closed like honestState.
const badge = (s: string): VerifyState =>
  s === "verified" || s === "honest_pending" ? (s as VerifyState) : "unbacked";

const fig = (key: string, raw: number, value: string, state = "honest_pending"): GstFigure => ({
  key,
  label: key,
  value,
  raw,
  state,
});

const RECON: GstDetailData["recon"] = {
  figures: [
    fig("available_2b_paise", 1800000, "₹18,000.00"),
    fig("claimed_paise", 2700000, "₹27,000.00"),
  ],
  rule_36_4: {
    rule_id: "GST-002",
    text: "ITC claimed exceeds 105% of GSTR-2B (Rule 36(4)).",
    statute: "CGST Rules 2017",
    section: "Rule 36(4)",
    itc_claimed_ratio: 1.5,
  },
  mismatches: [
    {
      id: 2,
      invoice_number: "B-2",
      gstin_supplier: "29BBBBB0000B1Z5",
      invoice_date: "2026-07-02",
      kind: "books_not_in_2b",
      note: "Claimed in books, missing from GSTR-2B — Rule 36(4) exposure.",
      figure: fig("itc_mismatch_tax_paise", 900000, "₹9,000.00"),
    },
  ],
};

describe("ReconPanel — every figure badged, mismatches named", () => {
  it("renders the aggregates, the Rule 36(4) citation, and each mismatch with its badge", () => {
    const html = renderToStaticMarkup(<ReconPanel recon={RECON} asOf="2026-07-23" badge={badge} />);
    expect(html).toContain("₹18,000.00");
    expect(html).toContain("CGST Rules 2017");
    expect(html).toContain("Rule 36(4)");
    // the mismatch row renders with its ₹ AND a badge chip — never an unbadged figure
    expect(html).toContain("B-2");
    expect(html).toContain("₹9,000.00");
    expect(html).toContain("Rule 36(4) exposure");
    expect(html).toContain("◐"); // honest_pending chip, not a fabricated ✓
    expect(html).not.toContain("✓");
  });

  it("an unknown badge state falls to ✕, never optimistically ✓", () => {
    const recon = { ...RECON, figures: [fig("x_paise", 1, "₹0.01", "someday-verified")] };
    const html = renderToStaticMarkup(<ReconPanel recon={recon} asOf="2026-07-23" badge={badge} />);
    expect(html).toContain("✕");
    expect(html).not.toContain("✓");
  });
});

describe("DownloadsPanel — export-gated, draft-IRN honesty label (WS9.3)", () => {
  const props = {
    draftIrnLabel: DRAFT_LABEL,
    period: "2026-07",
    invoice: "INV-9",
    error: null,
    onPeriod: () => {},
    onInvoice: () => {},
    onDownload: () => {},
  };

  it("renders the verbatim draft-IRN label on the e-invoice surface", () => {
    const html = renderToStaticMarkup(<DownloadsPanel canExport {...props} />);
    expect(html).toContain(DRAFT_LABEL);
    expect(html).toContain("GSTR-1 JSON");
  });

  it("is HIDDEN (not disabled) without the export capability — T11", () => {
    const html = renderToStaticMarkup(<DownloadsPanel canExport={false} {...props} />);
    expect(html).toBe("");
  });
});

const IMS: GstDetailData["ims"] = {
  invoices: [
    {
      id: "1",
      state: "pending",
      itc_eligible: false,
      reason: "awaiting action, deadline not yet reached",
      invoice_number: "M-1",
      gstin_supplier: "29AAAAA0000A1Z5",
      invoice_date: "2026-07-01",
      figure: fig("ims_itc_paise", 1800000, "₹18,000.00"),
    },
  ],
  eligible_itc_total: fig("ims_eligible_itc_total_paise", 0, "₹0.00"),
  deadline_pending_ca: true,
  deadline_note:
    "The GSTR-3B-linked deemed-acceptance deadline is not yet CA-sourced (BLOCKED-CA), so " +
    "deemed acceptance is NOT evaluated: an unactioned invoice stays pending. No date was guessed.",
};

const PREVIEW: ImsPreview = {
  committed: false,
  action: "accept",
  rows: [{ ...IMS.invoices[0], current_state: "pending", will_state: "accepted" }],
  skipped: [{ id: 99, reason: "Not in the ITC register — nothing was changed for it." }],
  eligible_itc_total_after: fig("ims_eligible_itc_total_paise", 1800000, "₹18,000.00"),
  deadline_note: IMS.deadline_note,
  preview_token: "tok",
};

describe("imsConfirmPlan — no server preview, no commit path", () => {
  it("offers exactly the previewed rows with the server token", () => {
    expect(imsConfirmPlan(PREVIEW)).toEqual({ action: "accept", ids: [1], preview_token: "tok" });
  });
  it("refuses without a token, after commit, on empty rows, or with no preview", () => {
    expect(imsConfirmPlan(null)).toBeNull();
    expect(imsConfirmPlan({ ...PREVIEW, preview_token: undefined })).toBeNull();
    expect(imsConfirmPlan({ ...PREVIEW, committed: true })).toBeNull();
    expect(imsConfirmPlan({ ...PREVIEW, rows: [] })).toBeNull();
  });
});

describe("ImsPanel — BLOCKED-CA stated, preview states the change and accounts for every id", () => {
  const props = {
    ims: IMS,
    badge,
    selected: new Set(["1"]),
    action: "accept" as const,
    busy: false,
    error: null,
    traceId: "t",
    onToggle: () => {},
    onAction: () => {},
    onPreview: () => {},
    onConfirm: () => {},
  };

  it("states the deemed-accept deadline is not evaluated (never a guessed date)", () => {
    const html = renderToStaticMarkup(<ImsPanel {...props} preview={null} />);
    expect(html).toContain("BLOCKED-CA");
    expect(html).toContain("No date was guessed");
  });

  it("the dry-run names each transition and each skipped id, and offers a confirm", () => {
    const html = renderToStaticMarkup(<ImsPanel {...props} preview={PREVIEW} />);
    expect(html).toContain("pending →");
    expect(html).toContain("accepted");
    expect(html).toContain("#99");
    expect(html).toContain("Confirm accept for 1 invoice(s)");
  });

  it("no confirm button without a preview token — the server mints tokens only on previews", () => {
    const html = renderToStaticMarkup(
      <ImsPanel {...props} preview={{ ...PREVIEW, preview_token: undefined }} />,
    );
    expect(html).not.toContain("Confirm accept");
  });
});

describe("ObligationsPanel — §0.6: pending-CA dates are stated, never guessed", () => {
  it("labels the profile and renders the pending-CA line per obligation", () => {
    const html = renderToStaticMarkup(
      <ObligationsPanel
        obligations={{
          profile: "qrmp",
          profile_source: "settings.gst_filing_profile",
          quarter: ["2026-07", "2026-08", "2026-09"],
          obligations: [
            { form: "PMT-06", kind: "deposit", frequency: "monthly", period: "2026-07", due_date: null, pending_ca: true },
          ],
          due_dates_note: "Statutory due dates for these obligations are not yet CA-sourced.",
        }}
      />,
    );
    expect(html).toContain("qrmp profile");
    expect(html).toContain("PMT-06");
    expect(html).toContain("statutory due date pending CA — not guessed");
  });

  it("obligationWhen uses an injected date when one exists, pending-CA text otherwise", () => {
    const base = { form: "GSTR-1", kind: "return", frequency: "quarterly", period: "q" };
    expect(obligationWhen({ ...base, due_date: "2026-10-13", pending_ca: false })).toBe(
      "due 2026-10-13",
    );
    expect(obligationWhen({ ...base, due_date: null, pending_ca: true })).toContain("pending CA");
  });
});
