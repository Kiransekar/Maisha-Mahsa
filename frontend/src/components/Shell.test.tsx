// r:health-wiring — pins P1-6's Shell-level mount: `ConnectionHealthStrip` must be visible on
// EVERY screen (Shell.tsx's <main>), not just on screens that separately wire their own health
// query. Nothing previously rendered `<Shell>` itself, so deleting that one mount line would have
// passed every other test in the repo silently.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { FRESHNESS_QUERY_KEY, type FreshnessData } from "./ConnectionHealth";
import { Shell } from "./Shell";

// The wiring test pre-seeds the query cache, so `useConnectionHealth()`'s `api()` call is never
// actually reached during a synchronous `renderToStaticMarkup` pass (no effects run — no fetch is
// kicked off). Mocked anyway to fail loudly rather than hit the network if that ever stops being
// true, matching Today.test.ts/Domain.test.ts.
vi.mock("../lib/api", () => ({
  api: vi.fn(async () => {
    throw new Error("Shell.test.tsx: api() should not be reached — the query cache is pre-seeded");
  }),
}));

function unhealthy(): FreshnessData {
  return {
    as_of: "2026-07-22",
    sources: [
      {
        key: "bank_feeds",
        label: "Bank feeds",
        last_updated: "2026-07-13",
        age_days: 9,
        threshold_days: 2,
        stale: true,
        synced: true,
        note: "past its 2-day freshness limit",
      },
    ],
    overall: {
      status: "stale",
      healthy: false,
      headline: "Bank feeds is 9 days old.",
      worst_age_days: 9,
      never_synced: [],
      stale: ["bank_feeds"],
    },
  };
}

function healthy(): FreshnessData {
  return {
    as_of: "2026-07-22",
    sources: [],
    overall: {
      status: "fresh",
      healthy: true,
      headline: "",
      worst_age_days: 0,
      never_synced: [],
      stale: [],
    },
  };
}

function renderShell(healthData: FreshnessData) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(FRESHNESS_QUERY_KEY, healthData);
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Shell>
          <p>screen content marker</p>
        </Shell>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Shell — mounts ConnectionHealthStrip once, visible on every screen", () => {
  it("surfaces the strip's own headline when a source is unhealthy", () => {
    // THE mutation this guards: deleting `<ConnectionHealthStrip />` from Shell.tsx's <main>.
    // Without the mount, this text has no path onto the page at all.
    const html = renderShell(unhealthy());
    expect(html).toContain("Bank feeds is 9 days old.");
  });

  it("stays quiet — no strip chrome at all — once every source is healthy", () => {
    const html = renderShell(healthy());
    expect(html).not.toContain("Where your data comes from");
  });

  it("still renders the screen's own children alongside the strip", () => {
    const html = renderShell(unhealthy());
    expect(html).toContain("screen content marker");
  });

  // WS10.4 — the in-product disclaimer must render on every screen, byte-for-byte the mirror
  // of app.core.legal.DISCLAIMER_TEXT (a paraphrase is not the disclaimer the ticket
  // specifies). JSX collapses whitespace to single spaces, matching the constant exactly.
  it("renders the byte-exact WS10.4 disclaimer on every screen", () => {
    const html = renderShell(healthy());
    expect(html).toContain(
      "software tool, not the practice of chartered accountancy; outputs require professional verification",
    );
  });
});
