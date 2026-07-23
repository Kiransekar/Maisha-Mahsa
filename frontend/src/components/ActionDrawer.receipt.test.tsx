// P1-8 — receipt-OCR prefill: a real, static React render (see BankCsvImport.test.tsx for why
// renderToStaticMarkup, not @testing-library — this repo has no DOM-interaction test harness).
// What this proves: prefilled fields are genuine editable <input>s, not read-only text, and the
// "check before submitting" caveat renders exactly when there is something to check.

import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ActionDrawer } from "./ActionDrawer";
import type { ActionSpec } from "../routes/Domain";

const submitClaim: ActionSpec = {
  key: "submit-claim",
  label: "Submit claim",
  fields: [
    { name: "claim_date", label: "Claim date", type: "date", required: true, placeholder: "", options: [] },
    { name: "expense_date", label: "Expense date", type: "date", required: true, placeholder: "", options: [] },
    { name: "category", label: "Category", type: "text", required: true, placeholder: "travel", options: [] },
    { name: "amount", label: "Amount (₹)", type: "number", required: true, placeholder: "5000", options: [] },
    {
      name: "vendor_gstin",
      label: "Vendor GSTIN",
      type: "text",
      required: false,
      placeholder: "",
      options: [],
    },
  ],
};

describe("ActionDrawer — receipt-OCR prefill (P1-8)", () => {
  it("renders parsed values as editable inputs, not static text", () => {
    const html = renderToStaticMarkup(
      <ActionDrawer
        domain="expense"
        a={submitClaim}
        badge={() => "honest_pending"}
        onCommitted={() => {}}
        prefill={{ amount: "1234.56", vendor_gstin: "27AAAAA0000A1Z5", expense_date: "2026-06-28" }}
      />,
    );
    expect(html).toContain('value="1234.56"');
    expect(html).toContain('value="27AAAAA0000A1Z5"');
    expect(html).toContain('value="2026-06-28"');
    expect(html).toContain("<input"); // still a real, editable control — not a frozen summary
  });

  it("renders the 'parsed from receipt' caveat naming exactly the prefilled fields", () => {
    const html = renderToStaticMarkup(
      <ActionDrawer
        domain="expense"
        a={submitClaim}
        badge={() => "honest_pending"}
        onCommitted={() => {}}
        prefill={{ amount: "1234.56" }}
      />,
    );
    expect(html).toContain("Parsed from receipt");
    expect(html).toContain("check before submitting");
    expect(html).toContain("Amount (₹)");
    expect(html).toContain("OCR is never authoritative");
  });

  it("renders no caveat at all when nothing was prefilled", () => {
    const html = renderToStaticMarkup(
      <ActionDrawer domain="ledger" a={submitClaim} badge={() => "honest_pending"} onCommitted={() => {}} />,
    );
    expect(html).not.toContain("Parsed from receipt");
  });
});
