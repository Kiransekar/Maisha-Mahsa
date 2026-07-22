// WS7.4 — the WORKING altitude: one domain, read all day by a CA or an accountant.
//
// BRAND_THEME §2b (Zoho): spacious shell, DENSE interior. Today/Domains are the marketing-adjacent
// altitude; this screen is Tally-grade — compact rows, tabular numerals, tight vertical rhythm.
// That density IS the point of the second altitude, so the section headings and gaps here are
// deliberately tighter than Today's `H2` (28px rhythm) rather than reusing it.
//
// Honesty rules (docs/WS7_BUILD_CONTRACT.md):
//   · Every figure's ✓/◐/✕ comes from the server's `state`, run through `honestState` — an
//     unrecognised state falls to ✕ and NOTHING reads ✓ while Mahsa is unreachable (invariant 6).
//   · Deadlines carry no ₹ figure on this endpoint, so the consequence line says it is not known.
//     It never renders ₹0 (invariant 2).
//   · The action registry is listed, not fired: there is no preview-then-confirm endpoint behind
//     `app.web.actions` (its handlers write immediately), and invariant 9 forbids a silent
//     mutation. The panel says so out loud rather than shipping a button that skips the preview.

import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import {
  VerifiedNumber,
  effectiveState,
  type VerifyState,
} from "../components/VerifiedNumber";
import { ErrorState } from "../components/ErrorState";
import { useTraceId } from "../lib/trace";
import { Empty, Header, MahsaDownBanner } from "./Today";

export type Figure = {
  key: string;
  label: string;
  value: string;
  raw: unknown;
  state: string;
};

export type Deadline = {
  domain: string | null;
  form_name: string | null;
  due_date: string;
  label: string;
  days_overdue?: number;
  days_to_due?: number;
};

export type ActionSpec = {
  key: string;
  label: string;
  fields: {
    name: string;
    label: string;
    type: string;
    required: boolean;
    placeholder: string;
    options: string[];
  }[];
};

export type DomainData = {
  domain: string;
  as_of: string;
  mahsa_up: boolean;
  mahsa_down_message: string | null;
  health: { status: string; score: number | null; requires_approval: boolean } | null;
  figures: Figure[];
  deadlines: Deadline[];
  actions: ActionSpec[];
};

// ── pure logic (tested in Domain.test.ts) ────────────────────────────────────

const KNOWN_STATES = ["verified", "honest_pending", "unbacked"];

/** The single gate every badge on both hub altitudes passes through.
 *
 *  Two independent ways a ✓ could be fabricated, both closed here:
 *    1. an unrecognised/missing `state` string — falls to ✕, never optimistically ✓ (invariant 1)
 *    2. `mahsa_up: false` — `/api/domains/{d}` derives `state` from Mahsa's static recompute-
 *       COVERAGE table, which does not know the sidecar is down, so a figure can arrive marked
 *       "verified" during an outage. Downgraded to ◐ here, reusing `effectiveState`. */
export function honestState(state: string | null | undefined, mahsaUp: boolean): VerifyState {
  const known: VerifyState = KNOWN_STATES.includes(state ?? "")
    ? (state as VerifyState)
    : "unbacked";
  return effectiveState(known, !mahsaUp);
}

/** Coverage as a sentence. Honest-empty ≠ zero: no figures says no figures, and during an
 *  outage nothing is claimed as verified (matching what `honestState` will actually render). */
export function coverageText(verified: number, total: number, mahsaUp: boolean): string {
  if (total === 0) return "no figures published on this domain yet";
  if (!mahsaUp) return `${total} figures · none verified while Mahsa is unreachable`;
  return `${verified} of ${total} figures recomputed`;
}

/** The "when" half of the alert grammar. The server sends `days_overdue` OR `days_to_due`
 *  depending on the branch it took — a missing count states the date rather than assuming 0,
 *  which would read as "due today" on a deadline we simply don't have the delta for. */
export function deadlineWhen(d: Deadline): { text: string; overdue: boolean } {
  const days = (n: number) => `${n} day${n === 1 ? "" : "s"}`;
  if (d.label === "OVERDUE") {
    const n = d.days_overdue;
    return {
      overdue: true,
      text:
        n === undefined || n === null
          ? `overdue — was due ${d.due_date}`
          : `overdue by ${days(n)} — was due ${d.due_date}`,
    };
  }
  const n = d.days_to_due;
  if (n === undefined || n === null) return { overdue: false, text: `due ${d.due_date}` };
  if (n === 0) return { overdue: false, text: `due today — ${d.due_date}` };
  return { overdue: false, text: `due in ${days(n)} — ${d.due_date}` };
}

// The ₹ half of the alert grammar. `/api/domains/{d}` ships the raw compliance calendar, which
// carries no penalty amount (unlike `/api/today`, which joins `ComplianceCalendar.penalty_amount`
// and the ported GSTR-3B late fee). Invariant 2: we say so, we do not print ₹0.
export const IMPACT_UNKNOWN = "₹ impact not yet known — we don't guess";

// ── screen ───────────────────────────────────────────────────────────────────

export function Domain() {
  const { domain = "" } = useParams();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["domain", domain],
    queryFn: () => api<DomainData>(`/domains/${encodeURIComponent(domain)}`),
  });
  const traceId = useTraceId(`domain-${domain}`);

  if (isLoading && !data) return <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>;

  // Anti-pattern #14: never a blank shell. Last-known figures render below the error, and the
  // `stale` flag downgrades every ✓ — a verified badge on data we could not refresh is the
  // exact trust failure the badge exists to prevent (T4).
  if (error) {
    return (
      <div>
        <Header title={domain} as_of={data?.as_of} />
        <ErrorState error={error} traceId={traceId} onRetry={refetch}>
          {data && (
            <>
              <Section>Last known — not current</Section>
              <FigureGrid figures={data.figures} mahsaUp={data.mahsa_up} asOf={data.as_of} stale />
            </>
          )}
        </ErrorState>
      </div>
    );
  }
  if (!data) return null;

  const verified = data.figures.filter((f) => honestState(f.state, data.mahsa_up) === "verified");

  return (
    <section>
      <Link to="/domains" style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>
        ← All domains
      </Link>
      <Header title={data.domain} as_of={data.as_of} />

      {!data.mahsa_up && <MahsaDownBanner />}

      {/* Dense header strip: the verdict, the score, and what fraction is actually recomputed. */}
      <div
        style={{
          display: "flex",
          gap: 24,
          flexWrap: "wrap",
          alignItems: "baseline",
          border: "1px solid var(--color-border)",
          background: "var(--color-surface)",
          borderRadius: 8,
          padding: "10px 14px",
          fontSize: 13,
        }}
      >
        <Stat label="Mahsa verdict">{data.health ? data.health.status : "not scored"}</Stat>
        <Stat label="Score">
          {data.health && data.health.score !== null ? (
            <span className="tnum">{data.health.score}</span>
          ) : (
            <span style={{ color: "var(--color-ink-faint)" }}>—</span>
          )}
        </Stat>
        <Stat label="Coverage">
          {coverageText(verified.length, data.figures.length, data.mahsa_up)}
        </Stat>
        {data.health?.requires_approval && (
          <Stat label="Sign-off">
            <Link to="/approvals" style={{ color: "var(--color-accent)" }}>
              needs your approval →
            </Link>
          </Stat>
        )}
      </div>

      <Section>Figures · {data.figures.length}</Section>
      {data.figures.length === 0 ? (
        <Empty>
          This domain publishes no snapshot figures yet. That is an unwired source, not a set of
          zeroes.
        </Empty>
      ) : (
        <>
          <p style={{ fontSize: 11, color: "var(--color-ink-faint)", margin: "0 0 8px" }}>
            Each badge comes from Mahsa's recompute-coverage table for that fact key. This endpoint
            does not yet ship the inputs → formula → citations trail, so the working panels below
            show the fact key and an unsealed verdict — an honest gap, not a sealed empty.
          </p>
          <FigureGrid figures={data.figures} mahsaUp={data.mahsa_up} asOf={data.as_of} />
        </>
      )}

      <Section>Deadlines · {data.deadlines.length}</Section>
      {data.deadlines.length === 0 ? (
        <Empty>No statutory deadline is in view for this domain today.</Empty>
      ) : (
        data.deadlines.map((d, i) => <DeadlineRow key={`${d.form_name}-${d.due_date}-${i}`} d={d} />)
      )}

      <Section>Actions · {data.actions.length}</Section>
      {data.actions.length === 0 ? (
        <Empty>No mutation is registered for this domain.</Empty>
      ) : (
        <>
          <p style={{ fontSize: 12, color: "var(--color-ink-muted)", margin: "0 0 8px" }}>
            These are listed, not armed. Every mutation in this product is preview-then-confirm —
            you see the exact rows and the total ₹ impact before anything is written — and the
            server handlers behind these actions write immediately, with no preview step. Until
            that preview exists they run on the HTMX screens only.
          </p>
          {data.actions.map((a) => (
            <ActionRow key={a.key} a={a} />
          ))}
        </>
      )}
    </section>
  );
}

function FigureGrid({
  figures,
  mahsaUp,
  asOf,
  stale = false,
}: {
  figures: Figure[];
  mahsaUp: boolean;
  asOf: string;
  stale?: boolean;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(232px, 1fr))",
        gap: 8, // dense interior: the 8px rung, not Today's 12
      }}
    >
      {figures.map((f) => (
        <VerifiedNumber
          key={f.key}
          label={f.label}
          value={f.value}
          state={honestState(f.state, mahsaUp)}
          asOf={asOf}
          stale={stale}
          // T7: every badged figure stays interrogable. Only what the server actually sent goes
          // in here — the fact key that decided the badge, and no invented formula or citation.
          working={{ inputs: [{ label: "Fact key", value: f.key }] }}
        />
      ))}
    </div>
  );
}

/** T5/T12 alert grammar in one compact row: what · when · ₹-consequence · one-tap action. */
function DeadlineRow({ d }: { d: Deadline }) {
  const when = deadlineWhen(d);
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        gap: 12,
        flexWrap: "wrap",
        border: "1px solid var(--color-border)",
        background: "var(--color-surface)",
        borderRadius: 4,
        padding: "7px 12px",
        marginBottom: 4,
        fontSize: 13,
      }}
    >
      <div>
        {/* Name the form, never "a compliance item" (BRAND_THEME §2b). */}
        <span>{d.form_name ?? "unnamed filing"}</span>{" "}
        <span
          className="tnum"
          style={{
            color: when.overdue ? "var(--color-money-out)" : "var(--color-ink-muted)",
            fontSize: 12,
          }}
        >
          {when.text}
        </span>
      </div>
      <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
        <span style={{ color: "var(--color-ink-faint)", fontSize: 12 }}>{IMPACT_UNKNOWN}</span>
        <Link to="/domains/compliance" style={{ color: "var(--color-accent)", fontSize: 12 }}>
          Compliance register →
        </Link>
      </div>
    </div>
  );
}

function ActionRow({ a }: { a: ActionSpec }) {
  return (
    <details
      style={{
        border: "1px solid var(--color-border)",
        background: "var(--color-surface)",
        borderRadius: 4,
        padding: "7px 12px",
        marginBottom: 4,
        fontSize: 13,
      }}
    >
      <summary style={{ cursor: "pointer", listStyle: "none" }}>
        {a.label} <span className="ident" style={{ color: "var(--color-ink-faint)" }}>{a.key}</span>
      </summary>
      <div style={{ fontSize: 12, color: "var(--color-ink-muted)", marginTop: 6 }}>
        {a.fields.length === 0
          ? "Takes no input."
          : a.fields.map((f) => (
              <div key={f.name} style={{ display: "flex", justifyContent: "space-between" }}>
                <span>
                  {f.label}
                  {f.required ? "" : " (optional)"}
                </span>
                <span className="ident" style={{ color: "var(--color-ink-faint)" }}>
                  {f.type}
                  {f.options.length > 0 ? `: ${f.options.join(" | ")}` : ""}
                </span>
              </div>
            ))}
      </div>
    </details>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
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
      <div>{children}</div>
    </div>
  );
}

/** Today's `H2` on a 28px rhythm; the working altitude runs at 16/6 so more rows fit a screen. */
export function Section({ children }: { children: React.ReactNode }) {
  return (
    <h2
      style={{
        fontSize: 12,
        textTransform: "uppercase",
        letterSpacing: "0.08em",
        color: "var(--color-ink-muted)",
        fontWeight: 500,
        margin: "16px 0 6px",
      }}
    >
      {children}
    </h2>
  );
}
