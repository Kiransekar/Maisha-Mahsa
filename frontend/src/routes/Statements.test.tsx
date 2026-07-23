// P1-5 — the honesty gates of the statements screen, asserted directly.
//
// Repo convention (see BankCsvImport.test.tsx): no jsdom/@testing-library — pure functions
// plus renderToStaticMarkup for a REAL React render of the presentational pieces.

import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  BalanceSheetPanel,
  GlTable,
  MONEY_UNKNOWN,
  TrialBalancePanel,
  figureValue,
  imbalanceMessage,
  toVerifyState,
  type GlData,
  type StmtFigure,
} from "./Statements";

const fig = (key: string, raw: number | null, value = "x", state = "honest_pending"): StmtFigure => ({
  key,
  label: key,
  value,
  raw,
  state,
});

const TB_BROKEN = {
  balanced: false,
  figures: [
    fig("total_debit_paise", 60000123, "₹6,00,001.23"),
    fig("total_credit_paise", 60000000, "₹6,00,000.00"),
    fig("trial_balance_diff_paise", 123, "₹1.23"),
  ],
};

describe("imbalance banners — a broken book must look broken", () => {
  it("renders an explicit trial-balance banner carrying the exact server diff", () => {
    const html = renderToStaticMarkup(<TrialBalancePanel tb={TB_BROKEN} />);
    expect(html).toContain("Trial balance does not tie out");
    expect(html).toContain("₹1.23"); // the payload's diff, not a client recomputation
    expect(html).toContain("do not file");
    expect(html).toContain('role="alert"');
  });

  it("renders NO banner when the book ties out", () => {
    const html = renderToStaticMarkup(
      <TrialBalancePanel tb={{ ...TB_BROKEN, balanced: true }} />,
    );
    expect(html).not.toContain("does not tie out");
    expect(html).not.toContain('role="alert"');
  });

  it("renders the balance-sheet equation failure as its own banner", () => {
    const bs = { balanced: false, figures: [fig("assets_paise", 100)] };
    const html = renderToStaticMarkup(<BalanceSheetPanel bs={bs} />);
    expect(html).toContain("Balance sheet equation fails");
    expect(imbalanceMessage("bs")).toContain("assets do not equal");
  });
});

describe("null money — we don't guess", () => {
  it("a null total renders the unknown sentence, never a figure or ₹0", () => {
    const tb = { balanced: true, figures: [fig("total_debit_paise", null, "None")] };
    const html = renderToStaticMarkup(<TrialBalancePanel tb={tb} />);
    // renderToStaticMarkup HTML-escapes the apostrophe, so assert the escape-free halves
    expect(html).toContain("not yet known");
    expect(html).toContain("t guess");
    expect(html).not.toContain("₹0");
    expect(html).not.toContain("None");
  });

  it("figureValue passes a real value through and replaces only null/undefined", () => {
    expect(figureValue({ raw: 0, value: "₹0.00" })).toBe("₹0.00"); // a genuine zero stays a zero
    expect(figureValue({ raw: null, value: "None" })).toBe(MONEY_UNKNOWN);
  });
});

describe("badge gate — server-decided, fail-closed", () => {
  it("clamps unknown/missing states to unbacked, never verified", () => {
    expect(toVerifyState("verified")).toBe("verified");
    expect(toVerifyState("honest_pending")).toBe("honest_pending");
    expect(toVerifyState("definitely-fine")).toBe("unbacked");
    expect(toVerifyState(null)).toBe("unbacked");
    expect(toVerifyState(undefined)).toBe("unbacked");
  });

  it("a hostile GL state renders ✕, and the running balance column comes from the payload", () => {
    const gl: GlData = {
      account_id: 1,
      code: "1000",
      name: "Cash",
      opening: fig("opening_balance_paise", 0, "₹0.00"),
      closing: fig("closing_balance_paise", 500000, "₹5,000.00"),
      state: "totally-legit-verified",
      lines: [
        { date: "2026-04-01", description: "seed", debit: 500000, credit: 0, balance: 500000 },
      ],
    };
    const html = renderToStaticMarkup(<GlTable gl={gl} />);
    expect(html).toContain("unbacked"); // hostile state fell to ✕
    expect(html).toContain("₹5,000.00"); // closing figure + totals row, tabular numerals
    expect(html).toContain("tnum");
    expect(html).toContain("Closing balance");
  });
});
