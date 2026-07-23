// P1-4 — the honesty gates of the CFO strategy screen, asserted directly.
//
// Repo convention (see Statements.test.tsx): no jsdom/@testing-library — pure functions
// plus renderToStaticMarkup for a REAL React render of the presentational pieces.

import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  CapTablePanel,
  InvestorPreviewCard,
  ScenarioOutcome,
  parseRupees,
  pctText,
  scenarioRunwayText,
  type InvestorPreviewData,
} from "./Cfo";

// ── scenario null-runway honesty (the ticket's load-bearing test) ────────────

describe("scenarioRunwayText — a null is never resolved in our favour", () => {
  it("an empty form has no runway, exactly as an empty ledger has none", () => {
    const t = scenarioRunwayText({ monthly_net_change: 0, months_to_zero: null }, false, 12);
    expect(t).toBe("nothing entered — no runway to compute");
  });

  it("null while cash-positive states the provable fact from the same payload", () => {
    const t = scenarioRunwayText({ monthly_net_change: 5000, months_to_zero: null }, true, 12);
    expect(t).toContain("not burning under this scenario");
  });

  it("null while BURNING states the horizon bound — never ∞ or 'unbounded'", () => {
    // burning, but opening cash outlasts the 12-month projection: months_to_zero is null.
    // "∞" here would be a fabrication — the server only projected 12 months.
    const t = scenarioRunwayText({ monthly_net_change: -1000, months_to_zero: null }, true, 12);
    expect(t).toContain("longer than the 12-month horizon");
    expect(t).toContain("don't guess");
    expect(t).not.toContain("∞");
    expect(t).not.toContain("unbounded");
  });

  it("a real depletion month renders as a bounded runway", () => {
    expect(scenarioRunwayText({ monthly_net_change: -1000, months_to_zero: 0 }, true, 12)).toBe(
      "cash goes negative in the first month",
    );
    expect(scenarioRunwayText({ monthly_net_change: -1000, months_to_zero: 6 }, true, 12)).toBe(
      "6 mo — cash goes negative in month 7",
    );
  });
});

describe("ScenarioOutcome — hypothetical figures never claim ✓", () => {
  const r = { monthly_net_change: -200000_00, balances: [], min_cash: 100000_00, months_to_zero: null };

  it("every outcome figure is ◐ with the hypothetical note; none is verified", () => {
    const html = renderToStaticMarkup(<ScenarioOutcome result={r} anyInput={true} horizonMonths={12} />);
    expect(html).not.toContain("✓");
    expect(html.match(/◐/g)?.length).toBe(3); // net change, min cash, runway — all pending
    expect(html).toContain("not recomputed by Mahsa");
    expect(html).toContain("₹"); // money renders through lib/money's Indian renderer
  });

  it("the runway card carries the honest horizon sentence when null-but-burning", () => {
    const html = renderToStaticMarkup(<ScenarioOutcome result={r} anyInput={true} horizonMonths={12} />);
    expect(html).toContain("longer than the 12-month horizon");
  });
});

// ── cap table ────────────────────────────────────────────────────────────────

describe("CapTablePanel", () => {
  const CAP = {
    total_shares: 100000,
    by_category: { founder: 70000, investor: 20000, esop: 10000 },
    pct: { founder: 0.7, investor: 0.2, esop: 0.1 },
  };

  it("renders every category with tabular-numeral shares and %", () => {
    const html = renderToStaticMarkup(<CapTablePanel cap={CAP} />);
    expect(html).toContain("founder");
    expect(html).toContain("70.0%");
    expect(html).toContain("20.0%");
    expect(html).toContain("70,000"); // Indian-grouped count
    expect(html).toContain("1,00,000");
    expect(html).toContain("tnum"); // BRAND_THEME §4: figures are tabular, non-negotiable
  });

  it("names the ESOP pool from the payload's own shares/pct", () => {
    const html = renderToStaticMarkup(<CapTablePanel cap={CAP} />);
    expect(html).toContain("ESOP pool");
    expect(html).toContain("10.0%");
  });

  it("an empty register is honest-empty, not a fabricated 100%/0% split", () => {
    const html = renderToStaticMarkup(
      <CapTablePanel cap={{ total_shares: 0, by_category: {}, pct: {} }} />,
    );
    expect(html).toContain("No shareholders on record");
    expect(html).not.toContain("100.0%");
  });

  it("states that no SAFE register endpoint exists rather than inventing balances", () => {
    const html = renderToStaticMarkup(<CapTablePanel cap={CAP} />);
    expect(html).toContain("no stored register endpoint");
  });
});

// ── investor preview ─────────────────────────────────────────────────────────

const UPD: InvestorPreviewData = {
  period: "2026-Q3",
  figures: [
    { key: "cash_paise", label: "Cash", value: "₹12,00,000.00", raw: 120000000, state: "honest_pending" },
    { key: "net_burn_paise", label: "Net burn", value: "₹2,00,000.00", raw: 20000000, state: "honest_pending" },
    { key: "ar_paise", label: "Ar", value: "₹0.00", raw: 0, state: "honest_pending" },
  ],
  runway_months: 6,
  accounts: 1,
  cap_table: { total_shares: 100000, ownership: { founder: 0.7, investor: 0.3 } },
  highlights: ["Closed seed round"],
  send_via: "/investor",
};

describe("InvestorPreviewCard", () => {
  it("renders period, badged figures, cap-table split and highlights from the payload", () => {
    const html = renderToStaticMarkup(<InvestorPreviewCard upd={UPD} />);
    expect(html).toContain("2026-Q3");
    expect(html).toContain("₹12,00,000.00");
    expect(html).toContain("◐"); // server-decided badge, honest by coverage map
    expect(html).not.toContain("✓"); // nothing here is Mahsa-ported — a ✓ would be minted
    expect(html).toContain("founder 70.0%");
    expect(html).toContain("Closed seed round");
    expect(html).toContain("6 mo"); // a real runway renders as the number
  });

  it("null runway with an EMPTY ledger reuses the WS7-E2E sentence — never ∞", () => {
    const html = renderToStaticMarkup(
      <InvestorPreviewCard upd={{ ...UPD, runway_months: null, accounts: 0 }} />,
    );
    expect(html).toContain("no ledger yet — no runway to compute");
    expect(html).not.toContain("∞");
  });

  it("null runway with accounts wired stays ambiguous: 'not yet known', never resolved", () => {
    const html = renderToStaticMarkup(
      <InvestorPreviewCard upd={{ ...UPD, runway_months: null, accounts: 3 }} />,
    );
    expect(html).toContain("not yet known");
    expect(html).toContain("t guess"); // staticMarkup escapes the apostrophe
    expect(html).not.toContain("∞");
  });

  it("send is a link-out to the existing surface; this page wires no send", () => {
    const html = renderToStaticMarkup(<InvestorPreviewCard upd={UPD} />);
    expect(html).toContain('href="/investor"');
    expect(html).toContain("Nothing is sent from this page");
    expect(html).not.toContain("<button"); // no send button exists to mis-click
  });

  it("an empty cap table in the update is honest-empty", () => {
    const html = renderToStaticMarkup(
      <InvestorPreviewCard
        upd={{ ...UPD, cap_table: { total_shares: 0, ownership: {} } }}
      />,
    );
    expect(html).toContain("No shareholders on record");
  });
});

// ── small pure helpers ───────────────────────────────────────────────────────

describe("parseRupees / pctText", () => {
  it("parses rupees to integer paise, rejecting junk and negatives as null", () => {
    expect(parseRupees("1200000")).toBe(120000000);
    expect(parseRupees("0")).toBe(0);
    expect(parseRupees("12.34")).toBe(1234);
    expect(parseRupees("")).toBeNull();
    expect(parseRupees("abc")).toBeNull();
    expect(parseRupees("-5")).toBeNull();
  });

  it("formats an ownership fraction, one decimal", () => {
    expect(pctText(0.7)).toBe("70.0%");
    expect(pctText(0.123456)).toBe("12.3%");
  });
});
