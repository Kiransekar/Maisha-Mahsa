// WS9.1 — the Tally import flow's pure gates and the report render. Same convention as
// BankCsvImport.test.tsx: no jsdom/@testing-library — pure predicates asserted directly, and
// renderToStaticMarkup for "the report renders what the server said".

import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  TallyReport,
  canCommitTally,
  drCr,
  mappingComplete,
  type MappingEntry,
  type ParseReport,
} from "./TallyImport";

const CLEAN_REPORT: ParseReport = {
  committed: false,
  counts: { ledger_masters: 4, vouchers: 3, voucher_lines: 6 },
  errors: [],
  unbalanced: [],
  reconciliation: [
    {
      name: "HDFC Bank",
      opening_paise: 0,
      debits_paise: 3000000,
      credits_paise: 1234567,
      computed_closing_paise: 1765433,
      stated_closing_paise: 1765433,
      match: true,
    },
    {
      name: "Sales",
      opening_paise: null,
      debits_paise: 0,
      credits_paise: 5000000,
      computed_closing_paise: -5000000,
      stated_closing_paise: null,
      match: null, // Tally stated no closing — unknown, never a fabricated pass
    },
  ],
  matched: [{ name: "HDFC Bank", account_id: 1, code: "1100" }],
  unmatched: [{ name: "Diesel Expense", parent: "Vehicle Running", suggested_type: "expense" }],
  accounts: [{ id: 1, code: "1100", name: "HDFC Bank", account_type: "asset" }],
  file_sha256: "abc",
  preview_token: "tok",
  confirm_word: "import",
};

const MAPPED: Record<string, MappingEntry> = {
  "Diesel Expense": { create: { code: "5200", name: "Diesel Expense", account_type: "expense" } },
};

describe("mappingComplete — every unmatched ledger must be resolved", () => {
  it("false while any unmatched name has no mapping", () => {
    expect(mappingComplete(CLEAN_REPORT, {})).toBe(false);
  });
  it("true for a complete create-new, and for an existing-account mapping", () => {
    expect(mappingComplete(CLEAN_REPORT, MAPPED)).toBe(true);
    expect(mappingComplete(CLEAN_REPORT, { "Diesel Expense": { account_id: 1 } })).toBe(true);
  });
  it("an incomplete create-new (blank code / bogus type) does not count as mapped", () => {
    expect(
      mappingComplete(CLEAN_REPORT, {
        "Diesel Expense": { create: { code: "", name: "Diesel Expense", account_type: "expense" } },
      }),
    ).toBe(false);
    expect(
      mappingComplete(CLEAN_REPORT, {
        "Diesel Expense": { create: { code: "5200", name: "Diesel", account_type: "petrol" } },
      }),
    ).toBe(false);
  });
});

describe("canCommitTally — the one gate the confirm button passes through", () => {
  it("armed only with a clean report, complete mapping, and the typed word", () => {
    expect(canCommitTally(CLEAN_REPORT, MAPPED, "import", false)).toBe(true);
    expect(canCommitTally(CLEAN_REPORT, MAPPED, "  IMPORT ", false)).toBe(true); // trims + case
  });
  it("never armed without the report, the word, or while a write is in flight", () => {
    expect(canCommitTally(null, MAPPED, "import", false)).toBe(false);
    expect(canCommitTally(CLEAN_REPORT, MAPPED, "", false)).toBe(false);
    expect(canCommitTally(CLEAN_REPORT, MAPPED, "yes", false)).toBe(false);
    expect(canCommitTally(CLEAN_REPORT, MAPPED, "import", true)).toBe(false);
  });
  it("never armed with an unmapped ledger, an exact-paise error, or an unbalanced voucher", () => {
    expect(canCommitTally(CLEAN_REPORT, {}, "import", false)).toBe(false);
    expect(
      canCommitTally({ ...CLEAN_REPORT, errors: ["voucher R-100: refusing to round"] }, MAPPED, "import", false),
    ).toBe(false);
    expect(
      canCommitTally(
        { ...CLEAN_REPORT, unbalanced: [{ voucher_id: "R-99", diff_paise: 1 }] },
        MAPPED,
        "import",
        false,
      ),
    ).toBe(false);
  });
  it("a file with zero vouchers imports nothing, so the button stays dark", () => {
    expect(
      canCommitTally(
        { ...CLEAN_REPORT, counts: { ...CLEAN_REPORT.counts, vouchers: 0 } },
        MAPPED,
        "import",
        false,
      ),
    ).toBe(false);
  });
});

describe("drCr — debit-positive paise rendered as Dr/Cr, exact", () => {
  it("renders sides and exact paise", () => {
    expect(drCr(1765433)).toContain("Dr");
    expect(drCr(1765433)).toContain("33 paise");
    expect(drCr(-5000000)).toContain("Cr");
    expect(drCr(0)).not.toContain("Dr");
  });
});

describe("TallyReport — renders the server's reconciliation report, mismatches first-class", () => {
  it("shows counts, the tie-out verdict per ledger, and 'not stated' rather than a guess", () => {
    const html = renderToStaticMarkup(
      <TallyReport
        report={CLEAN_REPORT}
        mapping={{}}
        setMapping={() => {}}
        confirmText=""
        setConfirmText={() => {}}
      />,
    );
    expect(html).toContain("nothing imported yet");
    expect(html).toContain("HDFC Bank");
    expect(html).toContain("not stated"); // Sales stated no closing — no fabricated match
    expect(html).toContain("Diesel Expense"); // the unmatched ledger needs a mapping row
    expect(html).toContain("Tally group: Vehicle Running");
    expect(html).toContain("every stated closing balance ties out");
  });
  it("with create-new selected, the Tally-group suggestion is shown beside the type picker", () => {
    const html = renderToStaticMarkup(
      <TallyReport
        report={CLEAN_REPORT}
        mapping={{
          "Diesel Expense": { create: { code: "", name: "Diesel Expense", account_type: "expense" } },
        }}
        setMapping={() => {}}
        confirmText=""
        setConfirmText={() => {}}
      />,
    );
    expect(html).toContain("suggested from the Tally group: expense");
  });
  it("lists an unbalanced voucher by its Tally id and blocks the confirm word input", () => {
    const html = renderToStaticMarkup(
      <TallyReport
        report={{ ...CLEAN_REPORT, unbalanced: [{ voucher_id: "R-99", diff_paise: 1 }] }}
        mapping={{}}
        setMapping={() => {}}
        confirmText=""
        setConfirmText={() => {}}
      />,
    );
    expect(html).toContain("R-99");
    expect(html).toContain("1 paise");
    expect(html).not.toContain("to arm the import");
    expect(html).toContain("refuses to guess");
  });
  it("a checksum mismatch is stated as NO, never absorbed", () => {
    const html = renderToStaticMarkup(
      <TallyReport
        report={{
          ...CLEAN_REPORT,
          reconciliation: [
            { ...CLEAN_REPORT.reconciliation[0], stated_closing_paise: 9999, match: false },
          ],
        }}
        mapping={{}}
        setMapping={() => {}}
        confirmText=""
        setConfirmText={() => {}}
      />,
    );
    expect(html).toContain("1 ledger(s) do NOT tie out");
    expect(html).toContain("NO");
  });
});
