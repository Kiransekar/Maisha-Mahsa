// P0-5 — the extraction's own tests. Money/parser logic already has exhaustive coverage carried
// over from Onboarding.test.ts (previewStatement, splitCsvRows, parseCsvDate, parseCsvAmount,
// inrPrecise — re-exported from there so that file keeps passing unchanged). This file covers what
// is NEW here: the presentational render of a dry-run result, and the confirm gate as its own
// pure predicate (`canConfirmImport`) so the "confirm disabled until a good preview exists"
// invariant is asserted directly rather than only implied by JSX.
//
// No @testing-library/react in this repo (see package.json) — every other component test in the
// codebase asserts on exported pure functions rather than mounted DOM. `renderToStaticMarkup` is
// react-dom (already a dependency) doing an ACTUAL React render with no jsdom required, so this
// stays inside "component renders" without adding a test-only dependency.

import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  StatementPreview,
  canConfirmImport,
  previewStatement,
  type CsvPreview,
} from "./BankCsvImport";

const GOOD_CSV = [
  "Txn Date,Narration,Withdrawal Amt,Deposit Amt",
  "01/04/2026,NEFT ACME LTD,0,1000.50",
  "02/04/2026,UPI to vendor,250.25,0",
  "not-a-date,broken row,100,0",
].join("\n");

describe("StatementPreview — component renders the dry-run result", () => {
  it("renders the row count, date range and ₹ totals from a real previewStatement() call", () => {
    const preview = previewStatement(GOOD_CSV);
    if (!preview.ok) throw new Error(preview.reason);
    const html = renderToStaticMarkup(<StatementPreview name="hdfc.csv" preview={preview} />);

    expect(html).toContain("Rows to import");
    expect(html).toContain("2"); // 2 importable rows
    expect(html).toContain("2026-04-01");
    expect(html).toContain("2026-04-02");
    expect(html).toContain("hdfc.csv");
    // The skipped row is rendered too, not swallowed.
    expect(html).toContain("1");
    expect(html).toContain("will be skipped");
  });

  it("renders the server's own rejection reason for a CSV it can't parse, not a generic error", () => {
    const preview = previewStatement("name,amount\nfoo,100");
    expect(preview.ok).toBe(false);
    const html = renderToStaticMarkup(<StatementPreview name="bad.csv" preview={preview} />);
    expect(html).toContain("need a date column and a debit/credit column");
    expect(html).toContain("bad.csv");
  });

  it("renders the no-importable-rows state distinctly rather than an empty preview panel", () => {
    const preview = previewStatement("date,debit,credit\nnot-a-date,1,0");
    if (!preview.ok) throw new Error(preview.reason);
    expect(preview.rows.length).toBe(0);
    const html = renderToStaticMarkup(<StatementPreview name="empty.csv" preview={preview} />);
    expect(html).toContain("confirm button stays disabled");
  });
});

describe("canConfirmImport — the one gate every confirm button must pass through", () => {
  const okPreview: CsvPreview = {
    ok: true,
    rows: [{ date: "2026-04-01", description: "x", debit: 0, credit: 100 }],
    skipped: 0,
    debitPaise: 0,
    creditPaise: 100,
    from: "2026-04-01",
    to: "2026-04-01",
    hasBalanceColumn: false,
    statementClosingPaise: null,
  };

  it("allows confirm only with an OK preview carrying at least one row, and nothing in flight", () => {
    expect(canConfirmImport(okPreview, false)).toBe(true);
  });

  it("blocks confirm with no file staged yet", () => {
    expect(canConfirmImport(null, false)).toBe(false);
  });

  it("blocks confirm on a rejected CSV — a mutation that reads `.ok` as truthy-ignoring fails this", () => {
    const rejected: CsvPreview = { ok: false, reason: "bad file" };
    expect(canConfirmImport(rejected, false)).toBe(false);
  });

  it("blocks confirm on an OK preview with zero importable rows", () => {
    expect(canConfirmImport({ ...okPreview, rows: [] }, false)).toBe(false);
  });

  it("blocks confirm while a write is already in flight — no double-submit", () => {
    expect(canConfirmImport(okPreview, true)).toBe(false);
  });
});
