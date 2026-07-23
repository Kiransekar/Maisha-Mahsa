// P1-6 — Today's cash strip must downgrade a ✓ the same way Approvals already does: on the
// server's own `state`, but ALSO on the real connection-health/payload-age check, not on
// `mahsa_up`/request-error alone. `CashStrip` is the one seam both the happy path and the
// last-known-on-error path go through (see Today.tsx), so this pins the wiring directly rather
// than only the pure `effectiveState` logic VerifiedNumber.test.ts already covers.
//
// r:health-wiring HONESTY NOTE: the `CashStrip`-level describe block below only pins CashStrip's
// OWN prop-forwarding — it never calls `Today()` itself, so it could not have caught (and did
// not catch) `Today()` computing `fresh.stale` and then hard-coding `stale={false}` at the call
// site instead of passing it through. The "Today() — the real wiring" block further down is what
// actually renders `Today()` end to end and closes that gap.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { FreshnessData } from "../components/ConnectionHealth";
import { FRESHNESS_QUERY_KEY } from "../components/ConnectionHealth";
import { CashStrip, Today } from "./Today";

// The real wiring test below pre-seeds the query cache, so `Today()`'s own `queryFn`/`api()` call
// is never actually reached during a synchronous `renderToStaticMarkup` pass (no effects run, so
// no fetch is kicked off) — mocked anyway per the ticket, and to fail loudly rather than hit the
// network if that ever stops being true.
vi.mock("../lib/api", () => ({
  api: vi.fn(async () => {
    throw new Error("Today.test.ts: api() should not be reached — the query cache is pre-seeded");
  }),
}));

const panel = (state: "verified" | "honest_pending" | "unbacked") => ({
  label: "Cash in bank",
  value: "₹12,34,567",
  state,
  note: null,
});

describe("CashStrip — a stale connection-health/payload-age check downgrades ✓, not just mahsa_up", () => {
  it("shows a plain ✓ for a verified figure when nothing is stale", () => {
    const html = renderToStaticMarkup(
      createElement(CashStrip, { panels: [panel("verified")], asOf: "2026-07-22", stale: false }),
    );
    expect(html).toContain("recomputed"); // the ✓ chip label
    expect(html).not.toContain("Downgraded from ✓");
  });

  it("downgrades a verified figure to ◐ when staleness is threaded through", () => {
    // THE mutation this guards: if Today() stops passing `fresh.stale` into CashStrip, or
    // CashStrip stops forwarding `stale` to VerifiedNumber, this figure keeps reading ✓ on
    // inputs nobody has confirmed are current — exactly the T4 failure this ticket closes.
    const html = renderToStaticMarkup(
      createElement(CashStrip, { panels: [panel("verified")], asOf: "2026-07-22", stale: true }),
    );
    expect(html).toContain("Downgraded from ✓");
    expect(html).not.toContain("✓ recomputed");
  });

  it("says 'we could not check' rather than 'stale' when freshness is unknown", () => {
    // Freshness = boolean | "unknown" — the two are different facts (T4) and must read
    // differently, the same distinction VerifiedNumber.tsx already enforces for stale itself.
    const html = renderToStaticMarkup(
      createElement(CashStrip, {
        panels: [panel("verified")],
        asOf: "2026-07-22",
        stale: "unknown",
      }),
    );
    // renderToStaticMarkup HTML-escapes the apostrophe, so match around it rather than on it.
    expect(html).toContain("check how fresh the inputs behind this figure are");
  });

  it("never upgrades an already-honest-pending figure", () => {
    const html = renderToStaticMarkup(
      createElement(CashStrip, {
        panels: [panel("honest_pending")],
        asOf: "2026-07-22",
        stale: true,
      }),
    );
    expect(html).not.toContain("Downgraded from ✓");
  });
});

// ── r:health-wiring: the real `Today()` component, not just CashStrip's own prop-forwarding ──

function health(over: Partial<FreshnessData["overall"]> = {}): FreshnessData {
  return {
    as_of: "2026-07-22",
    sources: [{
      key: "bank_feeds",
      label: "Bank feeds",
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

function todayData() {
  return {
    as_of: "2026-07-22",
    mahsa_up: true,
    cash_strip: [{ label: "Cash in bank", value: "₹12,34,567", state: "verified", note: null }],
    needs_you: [],
    trouble: [],
    penalties_avoided: { amount: "₹0", estimate: false, basis: "", component_count: 0 },
  };
}

/** Pre-seeds BOTH queries `Today()` reads so the very first (synchronous) render already reflects
 *  the steady state — no jsdom, no waiting on effects, matching this repo's renderToStaticMarkup
 *  convention (see auth.test.ts). */
function renderToday(healthData: FreshnessData) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(["today"], todayData());
  qc.setQueryData(FRESHNESS_QUERY_KEY, healthData);
  return renderToStaticMarkup(
    createElement(QueryClientProvider, { client: qc }, createElement(Today)),
  );
}

describe("Today() — the real wiring: booksFreshness() must actually reach the rendered cash strip", () => {
  it("downgrades the ✓ when the live /api/health/connections payload is stale", () => {
    // THE mutation this guards, that the CashStrip-only tests above cannot: if Today() stops
    // passing `stale={fresh.stale}` and hard-codes `stale={false}` instead, this figure keeps
    // reading ✓ on inputs the health check itself says are stale.
    const html = renderToday(health({ stale: ["bank_feeds"] }));
    expect(html).toContain("Downgraded from ✓");
  });

  it("keeps a plain ✓ when the live health payload says every source is current", () => {
    const html = renderToday(health());
    expect(html).toContain("recomputed"); // the ✓ chip label
    expect(html).not.toContain("Downgraded from ✓");
  });
});
