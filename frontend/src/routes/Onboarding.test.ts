// Pure logic only — the places onboarding could fabricate a value, hide a validation failure, or
// promise a verification it doesn't have (invariant 2/4: never invent a rupee; a heading must not
// assert a ✓ the payload didn't).
//
// `previewStatement` is the client-side dry run standing in for the missing server dry-run mode,
// so its job is to describe what `treasury/service.py :: import_csv` WILL do. The fixtures below
// are the divergence cases: comma-in-narration, sub-rupee amounts, unparsable dates, zero rows.

import { describe, expect, it } from "vitest";
import {
  figureHeading,
  inrPrecise,
  parseCsvAmount,
  parseCsvDate,
  pickFirstFigure,
  previewStatement,
  rupeesToPaise,
  splitCsvRows,
  validateGstin,
} from "./Onboarding";
import { honestState, type Figure } from "./Domain";

describe("validateGstin — format-only check, no fabricated lookup", () => {
  it("accepts a well-formed GSTIN", () => {
    expect(validateGstin("22AAAAA0000A1Z5")).toEqual({ valid: true, error: null });
  });

  it("rejects blank with a specific reason", () => {
    expect(validateGstin("").valid).toBe(false);
    expect(validateGstin("   ").error).toBe("GSTIN is required.");
  });

  it("rejects wrong length, naming the actual length", () => {
    const r = validateGstin("22AAAAA0000A1Z");
    expect(r.valid).toBe(false);
    expect(r.error).toContain("14");
  });

  it("rejects a right-length string that doesn't match the pattern", () => {
    const r = validateGstin("AAAAAAAAAAAAAAA");
    expect(r.valid).toBe(false);
    expect(r.error).toBe("Doesn't match the GSTIN format.");
  });

  it("uppercases before checking, so lowercase input is still accepted", () => {
    expect(validateGstin("22aaaaa0000a1z5").valid).toBe(true);
  });
});

describe("rupeesToPaise — the one money-parsing path in onboarding", () => {
  it("blank means 0 (opening balance is optional), not an error", () => {
    expect(rupeesToPaise("")).toBe(0);
    expect(rupeesToPaise("   ")).toBe(0);
  });

  it("converts rupees to integer paise exactly", () => {
    expect(rupeesToPaise("100")).toBe(10000);
    expect(rupeesToPaise("99.5")).toBe(9950);
  });

  it("returns null (not a fabricated 0) for unparsable or negative input", () => {
    expect(rupeesToPaise("not a number")).toBeNull();
    expect(rupeesToPaise("-50")).toBeNull();
  });
});

describe("inrPrecise — a sub-rupee total must never render as ₹0", () => {
  it("keeps the paise remainder visible", () => {
    expect(inrPrecise(40)).toBe("₹0 and 40 paise");
    expect(inrPrecise(123456)).toBe("₹1,234 and 56 paise");
  });

  it("renders a whole-rupee amount plainly, grouped Indian-style", () => {
    expect(inrPrecise(123400)).toBe("₹1,234");
    expect(inrPrecise(1234567800)).toBe("₹1,23,45,678");
  });

  it("does not lose the sign of a negative remainder", () => {
    expect(inrPrecise(-40)).toBe("₹0 and 40 paise");
    expect(inrPrecise(-10050)).toBe("-₹100 and 50 paise");
  });
});

describe("parseCsvAmount — mirrors service.py _parse_amount, exact paise", () => {
  it("parses rupee decimals to integer paise without float drift", () => {
    expect(parseCsvAmount("150.50")).toBe(15050);
    // 0.1 + 0.2 style drift: 1234.35 * 100 is 123434.99999 in binary float.
    expect(parseCsvAmount("1234.35")).toBe(123435);
    expect(parseCsvAmount("0.07")).toBe(7);
  });

  it("strips the separators Indian statements actually contain", () => {
    expect(parseCsvAmount("₹1,20,000.00")).toBe(12000000);
    expect(parseCsvAmount("Rs.500")).toBe(50000);
  });

  it("rounds half-up on a third decimal, as Decimal.quantize(ROUND_HALF_UP) does", () => {
    expect(parseCsvAmount("1.005")).toBe(101);
    expect(parseCsvAmount("1.004")).toBe(100);
  });

  it("returns 0 for the blank/dash forms the server also treats as 0", () => {
    expect(parseCsvAmount("")).toBe(0);
    expect(parseCsvAmount("-")).toBe(0);
    expect(parseCsvAmount("0.00")).toBe(0);
    expect(parseCsvAmount("N/A")).toBe(0);
  });
});

describe("parseCsvDate — the seven formats service.py accepts, and nothing else", () => {
  it("accepts every format in _DATE_FORMATS", () => {
    expect(parseCsvDate("2026-03-31")).toBe("2026-03-31");
    expect(parseCsvDate("31/03/2026")).toBe("2026-03-31");
    expect(parseCsvDate("31-03-2026")).toBe("2026-03-31");
    expect(parseCsvDate("31-Mar-2026")).toBe("2026-03-31");
    expect(parseCsvDate("31 Mar 2026")).toBe("2026-03-31");
  });

  it("reads a 2-digit year the way Python's %y does (00-68 -> 20xx, 69-99 -> 19xx)", () => {
    expect(parseCsvDate("01/04/26")).toBe("2026-04-01");
    expect(parseCsvDate("01/04/99")).toBe("1999-04-01");
  });

  it("is day-first, never month-first — 03/04 is 3 April, not 4 March", () => {
    expect(parseCsvDate("03/04/2026")).toBe("2026-04-03");
  });

  it("rejects an impossible date instead of rolling it over", () => {
    expect(parseCsvDate("31/02/2026")).toBeNull();
    expect(parseCsvDate("31/13/2026")).toBeNull();
    expect(parseCsvDate("not a date")).toBeNull();
  });
});

describe("splitCsvRows — quoted fields, because narrations contain commas", () => {
  it("keeps a quoted comma inside one cell", () => {
    expect(splitCsvRows('a,b\n"NEFT, ACME LTD",100')).toEqual([
      ["a", "b"],
      ["NEFT, ACME LTD", "100"],
    ]);
  });

  it("unescapes doubled quotes and handles CRLF", () => {
    expect(splitCsvRows('a\r\n"say ""hi"""')).toEqual([["a"], ['say "hi"']]);
  });

  it("drops all-blank rows, as csv reading in the service does", () => {
    expect(splitCsvRows("a,b\n , \nc,d")).toEqual([
      ["a", "b"],
      ["c", "d"],
    ]);
  });
});

describe("previewStatement — the dry run that must describe what import_csv will do", () => {
  const CSV = [
    "Txn Date,Narration,Withdrawal Amt,Deposit Amt",
    '01/04/2026,"NEFT, ACME LTD",0,1000.50',
    "02/04/2026,UPI to vendor,250.25,0",
    "not-a-date,broken row,100,0",
    "03/04/2026,zero row,0,0",
  ].join("\n");

  it("counts only the rows the server will actually insert", () => {
    const p = previewStatement(CSV);
    if (!p.ok) throw new Error(p.reason);
    expect(p.rows.length).toBe(2);
  });

  it("counts the silently-skipped rows — the bad date AND the all-zero row", () => {
    const p = previewStatement(CSV);
    if (!p.ok) throw new Error(p.reason);
    expect(p.skipped).toBe(2);
  });

  it("totals debits and credits in exact paise, not rounded rupees", () => {
    const p = previewStatement(CSV);
    if (!p.ok) throw new Error(p.reason);
    expect(p.creditPaise).toBe(100050);
    expect(p.debitPaise).toBe(25025);
  });

  it("reports the date range of the rows that will import, ignoring skipped ones", () => {
    const p = previewStatement(CSV);
    if (!p.ok) throw new Error(p.reason);
    expect([p.from, p.to]).toEqual(["2026-04-01", "2026-04-02"]);
  });

  it("refuses a CSV the server would reject, with the server's own reason", () => {
    const p = previewStatement("name,amount\nfoo,100");
    expect(p.ok).toBe(false);
    if (p.ok) return;
    expect(p.reason).toContain("need a date column and a debit/credit column");
  });

  it("reports zero importable rows rather than claiming an import will do something", () => {
    const p = previewStatement("date,debit,credit\nnot-a-date,1,0");
    if (!p.ok) throw new Error(p.reason);
    expect(p.rows).toEqual([]);
    expect(p.skipped).toBe(1);
    expect(p.from).toBeNull(); // no invented range for an empty set
  });
});

describe("pickFirstFigure — the payoff figure is never an arbitrary choice", () => {
  // figures[0] is deliberately NOT the verified one: any implementation that ignores the state
  // (or the mahsaUp flag) and just returns figures[0] must fail these.
  const figs: Figure[] = [
    { key: "a", label: "A", value: "1", raw: 1, state: "honest_pending" },
    { key: "b", label: "B", value: "2", raw: 2, state: "verified" },
    { key: "c", label: "C", value: "3", raw: 3, state: "verified" },
  ];

  it("prefers the first genuinely verified figure while Mahsa is up", () => {
    expect(pickFirstFigure(figs, true)?.key).toBe("b");
  });

  it("falls back to the first figure when nothing is verified", () => {
    const noneVerified: Figure[] = [{ key: "x", label: "X", value: "1", raw: 1, state: "honest_pending" }];
    expect(pickFirstFigure(noneVerified, true)?.key).toBe("x");
  });

  it("makes Mahsa's availability change the pick — a 'verified' figure wins nothing while it is down", () => {
    const up = pickFirstFigure(figs, true);
    const down = pickFirstFigure(figs, false);
    expect(up?.key).toBe("b"); // server-verified figure preferred over list order
    expect(down?.key).toBe("a"); // downgraded, so plain list order applies
    // The load-bearing assertion: if the state/mahsaUp logic is deleted and this just returns
    // figures[0], both calls return the SAME figure and this fails.
    expect(down?.key).not.toBe(up?.key);
    expect(honestState(down!.state, false)).not.toBe("verified");
  });

  it("returns null for no figures rather than a placeholder", () => {
    expect(pickFirstFigure([], true)).toBeNull();
  });
});

describe("figureHeading — the heading may not assert a ✓ the figure doesn't have", () => {
  it("only says 'verified' when the figure actually is", () => {
    expect(figureHeading("verified")).toBe("Your first verified figure");
  });

  it("never contains the word 'verified' for any unverified state", () => {
    for (const s of ["honest_pending", "unbacked", null] as const) {
      expect(figureHeading(s)).not.toContain("verified");
    }
  });

  it("says something neutral before a figure has loaded", () => {
    expect(figureHeading(null)).toBe("Your first figure");
  });
});

// Regression: import_csv (treasury/service.py:199-204) OVERWRITES the running balance from the
// file's own balance column. Asserting "net effect = credits - debits" on such a file invents a
// rupee figure the server will never produce.
describe("previewStatement — balance column changes what the import actually does", () => {
  const WITH_BAL = "date,description,debit,credit,balance\n01/04/2026,open,0,1000,50000\n02/04/2026,fee,200,0,49800\n";
  const NO_BAL = "date,description,debit,credit\n01/04/2026,open,0,1000\n02/04/2026,fee,200,0\n";

  it("detects the balance column and reports the statement's own closing balance", () => {
    const p = previewStatement(WITH_BAL);
    expect(p.ok).toBe(true);
    if (!p.ok) return;
    expect(p.hasBalanceColumn).toBe(true);
    // The LAST non-zero balance cell — what the server ends up recording, not 1000-200=800.
    expect(p.statementClosingPaise).toBe(4980000);
    expect(p.statementClosingPaise).not.toBe(p.creditPaise - p.debitPaise);
  });

  it("reports no balance column when the file has none, so a net effect is legitimate", () => {
    const p = previewStatement(NO_BAL);
    expect(p.ok).toBe(true);
    if (!p.ok) return;
    expect(p.hasBalanceColumn).toBe(false);
    expect(p.statementClosingPaise).toBeNull();
  });
});
