// WS7.4 — the OVERVIEW altitude: all twelve domains at a glance, then drill into one.
//
// This is the spacious half of the Zoho split (BRAND_THEME §2b); the density lives one click
// down in `Domain.tsx`. Everything honest about a badge is decided by `honestState` there and
// imported, so the two altitudes can never disagree about what counts as verified.
//
// Deliberate: the KPI strip carries NO verification chip. `/api/domains` sends those five as
// bare paise from direct ledger reads with no per-figure state, and inventing a badge in either
// direction would violate invariant 1 (a ✓ nobody recomputed) or slander a fine number with a ✕.
// The strip states what it is instead. Badged figures live on the domain pages.

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { inr } from "../lib/money";
import { ErrorState } from "../components/ErrorState";
import { useTraceId } from "../lib/trace";
import { Empty, H2, Header, MahsaDownBanner } from "./Today";
import { IMPACT_UNKNOWN, coverageText, deadlineWhen, type Deadline } from "./Domain";

type DomainRow = {
  key: string;
  score: number | null;
  status: string | null;
  color: string | null;
  requires_approval: boolean;
  coverage: { verified: number; total: number };
};

type Kpis = {
  cash: number;
  net_burn: number;
  runway_months: number | null;
  ar: number;
  ap: number;
  accounts: number;
};

// ── pure logic (tested in Domain.test.ts) ────────────────────────────────────

/** Honest-empty is not zero (invariant 3).
 *
 *  `collect_kpis` reads these straight off the ledger, so with no bank account wired every one of
 *  them arrives as a structural 0 — and `₹0` at 20px reads as a real, measured financial position.
 *  A new user with an empty ledger was being shown a confident zero cash and zero burn.
 *
 *  `null` here means "say it is unwired", not "render ₹0". Any non-zero figure is a real read and
 *  always renders, even with no accounts (AR/AP come from invoices, not from bank accounts). */
export function kpiValue(paise: number, accounts: number): string | null {
  if (paise === 0 && accounts === 0) return null;
  return inr(paise);
}

/** `treasury/service.py` sets `runway_months = None` when `net_burn == 0`, and
 *  `net_burn = max(0, burn - revenue)` is 0 in TWO unrelated situations:
 *
 *    a) revenue >= burn — genuinely not burning, runway really is unbounded;
 *    b) there were no transactions at all — an empty or unwired ledger, where there is no
 *       runway to speak of and "unbounded" is a flattering lie told to a new user.
 *
 *  The old copy asserted (a) unconditionally. We can only prove the empty case from
 *  `accounts === 0`; with accounts wired the payload carries neither `monthly_burn_paise` nor
 *  `monthly_revenue_paise`, so (a) and (b) are indistinguishable from here and we say so rather
 *  than pick the pleasant one. See the wiring note in the ticket report. */
export function runwayText(k: Pick<Kpis, "runway_months" | "accounts">): string {
  if (k.accounts === 0) return "no ledger yet — no runway to compute";
  if (k.runway_months === null) return "not yet known — we don't guess";
  return `${k.runway_months} mo`;
}

type DomainsData = {
  as_of: string;
  mahsa_up: boolean;
  mahsa_down_message: string | null;
  domains: DomainRow[];
  kpis: Kpis;
  deadlines: Deadline[];
};

export function Domains() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["domains"],
    queryFn: () => api<DomainsData>("/domains"),
  });
  const traceId = useTraceId("domains");

  if (isLoading && !data) return <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>;

  // Anti-pattern #14: a failure never renders an empty shell. Last-known rows come back marked
  // stale, and `mahsaUp={false}` is forced so no coverage line claims a live verification.
  if (error) {
    return (
      <div>
        <Header title="Domains" as_of={data?.as_of} />
        <ErrorState error={error} traceId={traceId} onRetry={refetch}>
          {data && (
            <>
              <H2>Last known — not current</H2>
              <DomainGrid domains={data.domains} mahsaUp={false} />
            </>
          )}
        </ErrorState>
      </div>
    );
  }
  if (!data) return null;

  return (
    <section>
      <Header title="Domains" as_of={data.as_of} />
      {!data.mahsa_up && <MahsaDownBanner />}

      <H2>Position</H2>
      <div
        style={{
          display: "flex",
          gap: 28,
          flexWrap: "wrap",
          border: "1px solid var(--color-border)",
          background: "var(--color-surface)",
          borderRadius: 8,
          padding: "14px 18px",
        }}
      >
        <MoneyKpi label="Cash" paise={data.kpis.cash} accounts={data.kpis.accounts} />
        <MoneyKpi label="Net burn / mo" paise={data.kpis.net_burn} accounts={data.kpis.accounts} />
        <Kpi label="Runway">
          {data.kpis.runway_months === null || data.kpis.accounts === 0 ? (
            <Prose>{runwayText(data.kpis)}</Prose>
          ) : (
            runwayText(data.kpis)
          )}
        </Kpi>
        <MoneyKpi label="Receivable" paise={data.kpis.ar} accounts={data.kpis.accounts} />
        <MoneyKpi label="Payable" paise={data.kpis.ap} accounts={data.kpis.accounts} />
      </div>
      <p style={{ fontSize: 11, color: "var(--color-ink-faint)", margin: "6px 0 0" }}>
        {data.kpis.accounts === 0
          ? "No bank account is wired to this ledger yet, so there is no position to read. What you see above is an empty source saying so — not a measured ₹0."
          : `Read straight from the ledger across ${data.kpis.accounts} account${data.kpis.accounts === 1 ? "" : "s"}.`}{" "}
        Mahsa has not recomputed these five, so they carry no verification state — the badged
        figures are on each domain page.
      </p>

      <H2>Domains · {data.domains.length}</H2>
      <DomainGrid domains={data.domains} mahsaUp={data.mahsa_up} />

      <H2>Compliance calendar · {data.deadlines.length}</H2>
      {data.deadlines.length === 0 ? (
        <Empty>No statutory deadline falls in the alert window today.</Empty>
      ) : (
        data.deadlines.map((d, i) => {
          const when = deadlineWhen(d);
          return (
            <div
              key={`${d.domain}-${d.form_name}-${d.due_date}-${i}`}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                gap: 16,
                flexWrap: "wrap",
                border: "1px solid var(--color-border)",
                background: "var(--color-surface)",
                borderRadius: 8,
                padding: "10px 14px",
                marginBottom: 6,
                fontSize: 13,
              }}
            >
              <div>
                <span>{d.form_name ?? "unnamed filing"}</span>{" "}
                <span
                  className="tnum"
                  style={{
                    fontSize: 12,
                    color: when.overdue ? "var(--color-money-out)" : "var(--color-ink-muted)",
                  }}
                >
                  {when.text}
                </span>
                <div style={{ fontSize: 12, color: "var(--color-ink-faint)" }}>
                  {IMPACT_UNKNOWN}
                </div>
              </div>
              <Link
                to={`/domains/${d.domain ?? "compliance"}`}
                style={{ color: "var(--color-accent)", fontSize: 12, whiteSpace: "nowrap" }}
              >
                Open {d.domain ?? "compliance"} →
              </Link>
            </div>
          );
        })
      )}
    </section>
  );
}

function DomainGrid({ domains, mahsaUp }: { domains: DomainRow[]; mahsaUp: boolean }) {
  if (domains.length === 0) return <Empty>No domain is registered.</Empty>;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
        gap: 12,
      }}
    >
      {domains.map((d) => (
        <Link
          key={d.key}
          to={`/domains/${d.key}`}
          style={{
            display: "block",
            textDecoration: "none",
            color: "inherit",
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)", // borders, not shadows
            borderRadius: 8,
            padding: "14px 16px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <span style={{ fontSize: 16, letterSpacing: "-0.01em" }}>{d.key}</span>
            {/* Health status stays achromatic on purpose: green/amber/red would bleed the money
                -direction ramp into a third meaning, and BRAND_THEME §4 keeps those families
                apart. Hierarchy here comes from size and tracking. */}
            <span className="tnum" style={{ fontSize: 13, color: "var(--color-ink-muted)" }}>
              {d.score === null ? "—" : d.score}
            </span>
          </div>
          <div style={{ fontSize: 12, color: "var(--color-ink-muted)", marginTop: 2 }}>
            {/* An unscored domain says unscored. Server-side an unknown status defaults to
                "green"; we do not restate a status Mahsa never produced. */}
            {mahsaUp && d.status ? d.status : "not scored — Mahsa unreachable"}
          </div>
          <div style={{ fontSize: 12, color: "var(--color-ink-faint)", marginTop: 6 }}>
            {coverageText(d.coverage.verified, d.coverage.total, mahsaUp)}
          </div>
          {d.requires_approval && (
            <div style={{ fontSize: 12, color: "var(--color-accent)", marginTop: 6 }}>
              needs your sign-off
            </div>
          )}
        </Link>
      ))}
    </div>
  );
}

/** A ledger figure, or — when the source is empty — a sentence admitting it, at prose size so it
 *  can never be mistaken for a number. */
function MoneyKpi({ label, paise, accounts }: { label: string; paise: number; accounts: number }) {
  const v = kpiValue(paise, accounts);
  return <Kpi label={label}>{v ?? <Prose>nothing wired yet — not ₹0</Prose>}</Kpi>;
}

function Prose({ children }: { children: React.ReactNode }) {
  return (
    <span style={{ fontSize: 13, color: "var(--color-ink-muted)" }}>{children}</span>
  );
}

function Kpi({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div
        style={{
          fontSize: 10,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: "var(--color-ink-faint)",
        }}
      >
        {label}
      </div>
      <div className="tnum" style={{ fontSize: 20, letterSpacing: "-0.02em" }}>
        {children}
      </div>
    </div>
  );
}
