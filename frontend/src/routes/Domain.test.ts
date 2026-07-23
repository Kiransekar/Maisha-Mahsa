// The three pure branches shared by both hub altitudes. Each one is a place a ✓ could be
// fabricated or a deadline could be misread, which is the only reason they are functions.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { FreshnessData } from "../components/ConnectionHealth";
import { FRESHNESS_QUERY_KEY } from "../components/ConnectionHealth";
import {
  coverageText,
  deadlineWhen,
  Domain,
  FigureGrid,
  honestState,
  ocrResultToPrefill,
  receiptDateToIso,
  vaultEmptyText,
  VaultResults,
  type Deadline,
  type DomainData,
  type Figure,
  type HistoryPoint,
  type VaultDoc,
} from "./Domain";
import { kpiValue, runwayText } from "./Domains";

// r:health-wiring: the wiring test below pre-seeds the query cache, so `Domain()`'s own `api()`
// call is never actually reached during a synchronous `renderToStaticMarkup` pass (no effects
// run — no fetch is kicked off). Mocked anyway per the ticket, and to fail loudly rather than hit
// the network if that ever stops being true.
vi.mock("../lib/api", () => ({
  api: vi.fn(async () => {
    throw new Error("Domain.test.ts: api() should not be reached — the query cache is pre-seeded");
  }),
}));

describe("honestState — a ✓ can only come from a live, recognised server state", () => {
  it("passes the three known states straight through while Mahsa is up", () => {
    expect(honestState("verified", true)).toBe("verified");
    expect(honestState("honest_pending", true)).toBe("honest_pending");
    expect(honestState("unbacked", true)).toBe("unbacked");
  });

  it("downgrades verified to ◐ when Mahsa is unreachable", () => {
    // THE case: /api/domains/{d} derives `state` from the static recompute-coverage table, so it
    // still says "verified" during an outage. Invariant 6 — nothing reads ✓ with the gate down.
    expect(honestState("verified", false)).toBe("honest_pending");
  });

  it("never promotes an unknown, empty or missing state to verified", () => {
    for (const bad of ["", "VERIFIED", "ok", "pending", "true", null, undefined]) {
      expect(honestState(bad, true)).toBe("unbacked");
    }
  });

  it("leaves an already-failing figure failing during an outage", () => {
    // A downgrade must never accidentally soften ✕ into ◐.
    expect(honestState("unbacked", false)).toBe("unbacked");
  });
});

describe("FigureGrid — P1-6: connection-health/payload-age staleness downgrades ✓ too, not just mahsaUp", () => {
  const figure = (state: string): Figure => ({
    key: "gst_payable",
    label: "GST payable",
    value: "₹1,000",
    raw: null,
    state,
  });

  it("keeps ✓ when Mahsa is up and nothing is stale", () => {
    const html = renderToStaticMarkup(
      createElement(FigureGrid, {
        figures: [figure("verified")],
        mahsaUp: true,
        asOf: "2026-07-22",
        stale: false,
      }),
    );
    expect(html).toContain("recomputed"); // the ✓ chip label
    expect(html).not.toContain("Downgraded from ✓");
  });

  it("downgrades to ◐ when `stale` is threaded through, even though Mahsa itself is up", () => {
    // THE mutation this guards: if Domain() stops passing the real `booksFreshness(...).stale`
    // into FigureGrid, or FigureGrid stops forwarding it to VerifiedNumber, a figure keeps
    // reading ✓ purely because Mahsa is reachable — the exact gap the "on the happy path we
    // never asked /api/health/connections" finding named.
    const html = renderToStaticMarkup(
      createElement(FigureGrid, {
        figures: [figure("verified")],
        mahsaUp: true,
        asOf: "2026-07-22",
        stale: true,
      }),
    );
    expect(html).toContain("Downgraded from ✓");
  });

  it("never upgrades a figure Mahsa itself did not back", () => {
    const html = renderToStaticMarkup(
      createElement(FigureGrid, {
        figures: [figure("unbacked")],
        mahsaUp: true,
        asOf: "2026-07-22",
        stale: true,
      }),
    );
    expect(html).not.toContain("Downgraded from ✓");
  });

  it("still applies the outage downgrade with `stale` defaulted (mahsaUp alone is enough)", () => {
    const html = renderToStaticMarkup(
      createElement(FigureGrid, { figures: [figure("verified")], mahsaUp: false, asOf: "2026-07-22" }),
    );
    // honestState() already downgrades a verified figure during an outage — confirms the default
    // `stale = false` doesn't mask that pre-existing behaviour.
    expect(html).toContain("not yet sealed"); // the ◐ chip label
  });
});

describe("FigureGrid — P2-3: trend sparklines are keyed to the figure's own fact key", () => {
  const figure = (key: string): Figure => ({
    key,
    label: "GST payable",
    value: "₹1,000",
    raw: null,
    state: "verified",
  });
  const pts = (...values: number[]): HistoryPoint[] =>
    values.map((value, i) => ({ captured_at: `2026-07-0${i + 1}`, value }));

  it("renders a sparkline for a figure with >=2 real captured points", () => {
    const html = renderToStaticMarkup(
      createElement(FigureGrid, {
        figures: [figure("gst_payable")],
        mahsaUp: true,
        asOf: "2026-07-22",
        history: { gst_payable: pts(100, 200) },
      }),
    );
    expect(html).toContain("<svg");
    expect(html).toContain("<polyline");
  });

  it("renders no sparkline when history is entirely absent", () => {
    const html = renderToStaticMarkup(
      createElement(FigureGrid, {
        figures: [figure("gst_payable")],
        mahsaUp: true,
        asOf: "2026-07-22",
      }),
    );
    expect(html).not.toContain("<svg");
  });

  it("MUTATION GUARD: a single real capture must not render a fabricated line", () => {
    // If FigureGrid (or Sparkline) ever padded a lone real point into a fake second one, this
    // would start rendering an <svg> — the exact fabrication the ticket's ≥2-point rule forbids.
    const html = renderToStaticMarkup(
      createElement(FigureGrid, {
        figures: [figure("gst_payable")],
        mahsaUp: true,
        asOf: "2026-07-22",
        history: { gst_payable: pts(100) },
      }),
    );
    expect(html).not.toContain("<svg");
  });

  it("never borrows another figure's series — an unrelated key's history stays absent here", () => {
    const html = renderToStaticMarkup(
      createElement(FigureGrid, {
        figures: [figure("gst_payable")],
        mahsaUp: true,
        asOf: "2026-07-22",
        history: { some_other_metric: pts(1, 2, 3) },
      }),
    );
    expect(html).not.toContain("<svg");
  });
});

describe("coverageText — honest-empty is not zero", () => {
  it("states that a domain has no figures rather than reporting 0 of 0", () => {
    expect(coverageText(0, 0, true)).toBe("no figures published on this domain yet");
  });

  it("claims nothing verified while Mahsa is down, whatever the server counted", () => {
    // The server's `coverage.verified` is computed from the same outage-blind table, so a
    // non-zero count arrives during an outage. It must not be restated as recomputed.
    expect(coverageText(7, 9, false)).not.toContain("recomputed");
    expect(coverageText(7, 9, false)).toContain("none verified");
  });

  it("reports the real fraction when the gate is up", () => {
    expect(coverageText(0, 9, true)).toBe("0 of 9 figures recomputed");
    expect(coverageText(9, 9, true)).toBe("9 of 9 figures recomputed");
  });
});

describe("runwayText — an ambiguous null is never resolved in our favour", () => {
  it("says the ledger is empty rather than claiming an unbounded runway", () => {
    // THE case: a brand-new user, zero accounts. net_burn == 0 because nothing exists, so the
    // server sends runway_months = null. "not burning — unbounded" would be a flattering lie.
    const t = runwayText({ runway_months: null, accounts: 0 });
    expect(t).toBe("no ledger yet — no runway to compute");
    expect(t).not.toContain("unbounded");
    expect(t).not.toContain("not burning");
  });

  it("refuses to claim 'not burning' from a null it cannot attribute", () => {
    // Accounts exist, but the payload carries no burn/revenue split — revenue >= burn and
    // no-transactions-this-window are indistinguishable here, so neither is asserted.
    const t = runwayText({ runway_months: null, accounts: 3 });
    expect(t).toBe("not yet known — we don't guess");
    expect(t).not.toContain("unbounded");
  });

  it("reports a real runway, including a fractional one", () => {
    expect(runwayText({ runway_months: 7.25, accounts: 2 })).toBe("7.25 mo");
    expect(runwayText({ runway_months: 0, accounts: 2 })).toBe("0 mo");
  });
});

describe("kpiValue — an empty source is not a ₹0 position", () => {
  it("returns null (say it is unwired) for a zero read with no account wired", () => {
    expect(kpiValue(0, 0)).toBeNull();
  });

  it("renders a genuine zero once accounts exist", () => {
    // Zero cash across two real accounts IS a measured fact and must not be hidden.
    expect(kpiValue(0, 2)).toBe("₹0");
  });

  it("always renders a non-zero figure, even with no bank account (AR/AP come from invoices)", () => {
    expect(kpiValue(1_23_45_600, 0)).toBe("₹1,23,456");
    expect(kpiValue(-50_00, 0)).toBe("-₹50");
  });

  it("groups in lakh/crore, not thousands", () => {
    expect(kpiValue(1_00_00_000_00, 1)).toBe("₹1,00,00,000");
  });
});

describe("receiptDateToIso — a day-first receipt date, or an honest blank", () => {
  it("trusts a bare ISO date as-is", () => {
    expect(receiptDateToIso("2026-07-01")).toBe("2026-07-01");
  });

  it("reorders DD/MM/YYYY and DD-MM-YYYY (day first) into ISO", () => {
    expect(receiptDateToIso("28/06/2026")).toBe("2026-06-28");
    expect(receiptDateToIso("28-06-2026")).toBe("2026-06-28");
  });

  it("never guesses a month/day swap on a shape it does not recognise", () => {
    expect(receiptDateToIso("Jun 28 2026")).toBe("");
    expect(receiptDateToIso(null)).toBe("");
  });
});

describe("ocrResultToPrefill — OCR only ever prefills the form's own fields", () => {
  it("maps amount_paise to rupees, gstin and the ISO date", () => {
    expect(ocrResultToPrefill({ amount_paise: 123456, gstin: "27AAAAA0000A1Z5", date: "28/06/2026" }))
      .toEqual({ amount: "1234.56", vendor_gstin: "27AAAAA0000A1Z5", expense_date: "2026-06-28" });
  });

  it("a genuine zero amount still prefills (not treated as 'nothing found')", () => {
    expect(ocrResultToPrefill({ amount_paise: 0, gstin: null, date: null })).toEqual({ amount: "0" });
  });

  it("omits any field OCR could not read rather than prefilling a guess", () => {
    expect(ocrResultToPrefill({ amount_paise: null, gstin: null, date: null })).toEqual({});
  });
});

describe("deadlineWhen — the 'when' half of the alert grammar", () => {
  const base: Deadline = { domain: "gst", form_name: "GSTR-3B", due_date: "2026-07-20", label: "T-7" };

  it("says overdue, by how much, and what the date was", () => {
    const w = deadlineWhen({ ...base, label: "OVERDUE", days_overdue: 3 });
    expect(w.overdue).toBe(true);
    expect(w.text).toBe("overdue by 3 days — was due 2026-07-20");
  });

  it("singularises one day on both branches", () => {
    expect(deadlineWhen({ ...base, label: "OVERDUE", days_overdue: 1 }).text).toContain("1 day —");
    expect(deadlineWhen({ ...base, days_to_due: 1 }).text).toContain("in 1 day —");
  });

  it("distinguishes due-today from a missing day count", () => {
    // 0 is a real "today"; absent is not — assuming 0 would invent an urgency we weren't told.
    expect(deadlineWhen({ ...base, days_to_due: 0 }).text).toBe("due today — 2026-07-20");
    expect(deadlineWhen(base).text).toBe("due 2026-07-20");
    expect(deadlineWhen(base).overdue).toBe(false);
  });

  it("still reports overdue when the server omitted the day count", () => {
    const w = deadlineWhen({ ...base, label: "OVERDUE" });
    expect(w.overdue).toBe(true);
    expect(w.text).toBe("overdue — was due 2026-07-20");
  });
});

// ── T11 field-level RBAC: a masked domain figure is a visible lock, never a false badge ──────
// The server (app.core.landing.mask_field) stripped the value; the SPA must state the
// restriction with its reason — not render a blank slot, and not route the shape through
// VerifiedNumber (whose honestState would show a false ✕ on a value that exists server-side).

describe("FigureGrid — T11 restricted figures render the lock chip with the server's reason", () => {
  const masked = {
    restricted: true as const,
    reason: "requires salary_detail clearance",
    key: "monthly_net_paise",
    label: "Monthly net paise",
  };

  it("renders the label, 'restricted', and the reason; no badge chip", () => {
    const html = renderToStaticMarkup(
      createElement(FigureGrid, { figures: [masked], mahsaUp: true, asOf: "2026-07-22" }),
    );
    expect(html).toContain("Monthly net paise");
    expect(html).toContain("restricted");
    expect(html).toContain("requires salary_detail clearance");
    // no verification chip on a value this role cannot see
    expect(html).not.toContain("recomputed");
    expect(html).not.toContain("not yet sealed");
  });

  it("renders unmasked siblings normally alongside a masked figure", () => {
    const ok: Figure = {
      key: "total_gross",
      label: "Total gross",
      value: "₹99,000",
      raw: 9_900_000,
      state: "verified",
    };
    const html = renderToStaticMarkup(
      createElement(FigureGrid, {
        figures: [masked, ok],
        mahsaUp: true,
        asOf: "2026-07-22",
        stale: false,
      }),
    );
    expect(html).toContain("₹99,000");
    expect(html).toContain("recomputed"); // the sibling keeps its honest ✓
    expect(html).toContain("requires salary_detail clearance");
  });
});

// ── r:health-wiring: the real `Domain()` component, not just FigureGrid's own prop-forwarding ──
// The FigureGrid describe block above pins FigureGrid's own forwarding of a `stale` prop it is
// handed directly — it never calls `Domain()`, so it could not have caught (and did not catch)
// `Domain()` computing `fresh.stale` and then hard-coding `stale={false}` (or dropping it) on the
// happy-path `<FigureGrid ... stale={stale} />` call inside `DomainBody`.

function health(over: Partial<FreshnessData["overall"]> = {}): FreshnessData {
  return {
    as_of: "2026-07-22",
    sources: [{
      key: "gst_filings",
      label: "GST filings",
      last_updated: "2026-07-13",
      age_days: 9,
      threshold_days: 2,
      stale: true,
      synced: true,
      note: "past its 2-day freshness limit",
    }],
    overall: {
      status: "fresh",
      healthy: true,
      headline: "",
      worst_age_days: 0,
      never_synced: [],
      stale: [],
      ...over,
    },
  };
}

function domainData(): DomainData {
  return {
    domain: "gst",
    as_of: "2026-07-22",
    mahsa_up: true,
    mahsa_down_message: null,
    health: null,
    figures: [{ key: "gst_payable", label: "GST payable", value: "₹1,000", raw: 1_00_000, state: "verified" }],
    deadlines: [],
    actions: [],
  };
}

/** Pre-seeds BOTH queries `Domain()` reads so the very first (synchronous) render already
 *  reflects the steady state — matching Today.test.ts's wiring-test approach. */
function renderDomain(healthData: FreshnessData) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["domain", "gst"], domainData());
  qc.setQueryData(FRESHNESS_QUERY_KEY, healthData);
  return renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(
        MemoryRouter,
        { initialEntries: ["/d/gst"] },
        createElement(
          Routes,
          null,
          createElement(Route, { path: "/d/:domain", element: createElement(Domain) }),
        ),
      ),
    ),
  );
}

describe("Domain() — the real wiring: booksFreshness() must actually reach the rendered figure grid", () => {
  it("downgrades the ✓ when the live /api/health/connections payload is stale", () => {
    // THE mutation this guards, that the FigureGrid-only tests above cannot: if Domain()/
    // DomainBody stops passing the real `stale` through to FigureGrid, this figure keeps reading
    // ✓ though the live health check says its source is stale.
    const html = renderDomain(health({ stale: ["gst_filings"] }));
    expect(html).toContain("Downgraded from ✓");
  });

  it("keeps a plain ✓ when the live health payload says every source is current", () => {
    const html = renderDomain(health());
    expect(html).toContain("recomputed"); // the ✓ chip label
    expect(html).not.toContain("Downgraded from ✓");
  });
});

// ── P2-1: vault browser — search/list, integrity state, retention, and role-clearance lock chips ──

describe("vaultEmptyText — an empty vault and an empty search result are different facts", () => {
  it("says the vault itself is empty when there was no query", () => {
    expect(vaultEmptyText("")).toBe("No documents are in the vault yet.");
    expect(vaultEmptyText("   ")).toBe("No documents are in the vault yet.");
  });

  it("names the query on a genuine no-match", () => {
    expect(vaultEmptyText("acme")).toBe("No document matches “acme”.");
  });
});

describe("VaultResults — renders real hits, an honest empty state, and loud integrity failures", () => {
  const okDoc: VaultDoc = {
    id: "1",
    file_name: "invoice.pdf",
    doc_type: "invoice",
    sensitivity: "internal",
    retention_until: "2035-03-31",
    retention_overdue: false,
    restricted: false,
    integrity_ok: true,
  };

  it("renders the honest empty state instead of a blank list when there are no hits", () => {
    const html = renderToStaticMarkup(createElement(VaultResults, { hits: [], query: "acme" }));
    expect(html).toContain("No document matches “acme”.");
  });

  it("renders a healthy document with its retention and a quiet SHA-256-ok chip", () => {
    const html = renderToStaticMarkup(createElement(VaultResults, { hits: [okDoc], query: "" }));
    expect(html).toContain("invoice.pdf");
    expect(html).toContain("✓ SHA-256 verified");
    expect(html).toContain("2035-03-31");
    expect(html).not.toContain("INTEGRITY CHECK FAILED");
  });

  it("renders an integrity failure LOUDLY — the ✕ chip AND a standalone alert block", () => {
    // THE mutation this guards: a doc whose content no longer hashes to its stored SHA-256 must
    // not read the same as a healthy one, or as a quiet ◐ — it gets its own alert.
    const html = renderToStaticMarkup(
      createElement(VaultResults, { hits: [{ ...okDoc, integrity_ok: false }], query: "" }),
    );
    expect(html).toContain("✕ INTEGRITY CHECK FAILED");
    expect(html).toContain("no longer matches its recorded SHA-256 hash");
  });

  it("flags a retention-overdue document without claiming an integrity problem", () => {
    const html = renderToStaticMarkup(
      createElement(VaultResults, {
        hits: [{ ...okDoc, retention_until: "2020-01-01", retention_overdue: true }],
        query: "",
      }),
    );
    expect(html).toContain("overdue for archival");
    expect(html).not.toContain("INTEGRITY CHECK FAILED");
  });

  it("renders a restricted document as a visible lock, never its content and never absent", () => {
    // Server-enforced clearance (VaultService.browse / app.core.landing.can_view_sensitivity):
    // the row still appears — existence is not hidden — but with a lock chip and reason, and no
    // integrity/retention detail (this role never received the content to verify).
    const html = renderToStaticMarkup(
      createElement(VaultResults, {
        hits: [
          {
            id: "2",
            file_name: "board-minutes.pdf",
            doc_type: "board_resolution",
            sensitivity: "restricted",
            retention_until: null,
            retention_overdue: false,
            restricted: true,
            reason: "requires restricted clearance",
          },
        ],
        query: "",
      }),
    );
    expect(html).toContain("board-minutes.pdf");
    expect(html).toContain("restricted — requires restricted clearance");
    expect(html).not.toContain("SHA-256");
  });

  it("renders healthy and restricted documents side by side without cross-contaminating state", () => {
    const html = renderToStaticMarkup(
      createElement(VaultResults, {
        hits: [
          okDoc,
          {
            id: "2",
            file_name: "cap-table.pdf",
            doc_type: "cap_table",
            sensitivity: "restricted",
            retention_until: null,
            retention_overdue: false,
            restricted: true,
            reason: "requires restricted clearance",
          },
        ],
        query: "",
      }),
    );
    expect(html).toContain("invoice.pdf");
    expect(html).toContain("✓ SHA-256 verified");
    expect(html).toContain("cap-table.pdf");
    expect(html).toContain("restricted — requires restricted clearance");
  });

  // CITE.P1-2: the `/d/vault?doc=<sha>` deep-link from a citation's working panel.
  it("highlights the deep-linked document and says why", () => {
    const html = renderToStaticMarkup(
      createElement(VaultResults, { hits: [okDoc], query: "", highlightId: "1" }),
    );
    expect(html).toContain("Cited source document — linked from a citation.");
    expect(html).not.toContain("is not in these results");
  });

  it("states honestly when the deep-linked document is not in the results", () => {
    const html = renderToStaticMarkup(
      createElement(VaultResults, {
        hits: [okDoc],
        query: "",
        highlightId: "deadbeefdeadbeefdeadbeef",
      }),
    );
    expect(html).toContain("The cited document (deadbeefdead…) is not in these results.");
    expect(html).not.toContain("Cited source document");
  });

  it("renders no citation highlight or missing-doc note without a deep-link", () => {
    const html = renderToStaticMarkup(createElement(VaultResults, { hits: [okDoc], query: "" }));
    expect(html).not.toContain("Cited source document");
    expect(html).not.toContain("is not in these results");
  });
});
