// P1-4 — /cfo: the CFO strategy screen, mirroring the HTMX /cfo + /investor pages over
// EXISTING endpoints only:
//   1. Scenario runner  → POST /api/forecast/scenario (untouched; pure compute)
//   2. Cap table        → GET  /api/equity/cap-table  (untouched)
//   3. Investor update  → POST /api/investor/preview  (thin wrapper over the same
//      app.core.strategy.investor_update generator the HTMX pages render). Sending stays
//      on the HTMX/email surface — this screen links out and wires NO send.
//
// Honesty rules (docs/WS7_BUILD_CONTRACT.md):
//   · Every figure renders through VerifiedNumber. The forecast/equity endpoints carry no
//     verdict machinery, so those figures ship the fail-closed ◐ — a client can never mint
//     a ✓ (§0.4); the investor-preview figures carry the server's badge_state verbatim.
//   · A null runway is never resolved in our favour (the WS7-E2E fix): the investor
//     preview reuses runwayText from Domains.tsx VERBATIM, and the scenario runner applies
//     the same don't-guess logic to the projection horizon (scenarioRunwayText below).
//   · Null/unknown money renders the "not yet known" sentence, never ₹0 (invariant 2).

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { inr, countIn } from "../lib/money";
import { VerifiedNumber } from "../components/VerifiedNumber";
import { ErrorState } from "../components/ErrorState";
import { useTraceId } from "../lib/trace";
import { Empty, H2, Header } from "./Today";
import { runwayText } from "./Domains";
import { figureValue, toVerifyState, type StmtFigure } from "./Statements";

// ── wire contracts ───────────────────────────────────────────────────────────

export type ScenarioResultData = {
  monthly_net_change: number; // signed paise; negative = burn
  balances: number[];
  min_cash: number;
  months_to_zero: number | null; // null = cash never went negative WITHIN the horizon
};

export type CapTableData = {
  total_shares: number;
  by_category: Record<string, number>;
  pct: Record<string, number>; // fraction by category
};

export type InvestorPreviewData = {
  period: string;
  figures: StmtFigure[];
  runway_months: number | null;
  accounts: number;
  cap_table: { total_shares: number; ownership: Record<string, number> };
  highlights: string[];
  send_via: string;
};

// ── pure logic (tested in Cfo.test.tsx) ──────────────────────────────────────

/** A rupee form field → integer paise. null on empty/invalid/negative — never a guess. */
export function parseRupees(s: string): number | null {
  if (s.trim() === "") return null;
  const n = Number(s);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * 100);
}

/**
 * The scenario twin of Domains.runwayText — same law (an ambiguous null is never resolved
 * in our favour), applied to a bounded projection:
 *   · nothing entered → say so; an empty form has no runway, exactly as an empty ledger
 *     has none (the WS7-E2E fix's distinction, reused, not regressed);
 *   · months_to_zero=null with net ≥ 0 → provably not burning UNDER THIS SCENARIO (the
 *     net is in the same server response — no client math);
 *   · months_to_zero=null while burning → the projection only covered `horizon` months.
 *     "∞ / unbounded" here would be a fabrication — we state the bound instead.
 */
export function scenarioRunwayText(
  r: Pick<ScenarioResultData, "monthly_net_change" | "months_to_zero">,
  anyInput: boolean,
  horizonMonths: number,
): string {
  if (!anyInput) return "nothing entered — no runway to compute";
  if (r.months_to_zero !== null) {
    return r.months_to_zero === 0
      ? "cash goes negative in the first month"
      : `${r.months_to_zero} mo — cash goes negative in month ${r.months_to_zero + 1}`;
  }
  if (r.monthly_net_change >= 0) return "not burning under this scenario — cash does not run out";
  return `longer than the ${horizonMonths}-month horizon — not projected beyond that, we don't guess`;
}

/** Ownership fraction → "61.5%". Not money — money never goes near this. */
export function pctText(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}


// A projection is arithmetic on the CFO's own hypothetical inputs — Mahsa recomputes book
// figures, not hypotheticals, so ◐ (with this note) is the honest permanent state here.
const SCENARIO_NOTE =
  "Hypothetical projection from the inputs above — not a book figure, and not recomputed by Mahsa.";

// ── presentational (pure; render-tested without a DOM) ──────────────────────

export function ScenarioOutcome({
  result,
  anyInput,
  horizonMonths,
}: {
  result: ScenarioResultData;
  anyInput: boolean;
  horizonMonths: number;
}) {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
      <VerifiedNumber
        label="Net change / mo under scenario"
        value={inr(result.monthly_net_change)}
        state="honest_pending" // no verdict machinery behind this endpoint; ◐ is the absence of a claim
        note={SCENARIO_NOTE}
      />
      <VerifiedNumber
        label={`Minimum cash over ${horizonMonths} months`}
        value={inr(result.min_cash)}
        state="honest_pending"
        note={SCENARIO_NOTE}
      />
      <VerifiedNumber
        label="Runway under scenario"
        value={scenarioRunwayText(result, anyInput, horizonMonths)}
        state="honest_pending"
        note={SCENARIO_NOTE}
      />
    </div>
  );
}

export function CapTablePanel({ cap }: { cap: CapTableData }) {
  if (cap.total_shares === 0) {
    return (
      <Empty>
        No shareholders on record — this is an empty register, not a 100%/0% split. Add them
        under the equity domain.
      </Empty>
    );
  }
  const esop = cap.by_category["esop"] ?? 0;
  return (
    <div
      style={{
        border: "1px solid var(--color-border)",
        background: "var(--color-surface)",
        borderRadius: 8,
        overflow: "hidden",
      }}
    >
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ background: "var(--color-surface-sunk)" }}>
            <th style={{ ...TH, textAlign: "left" }}>Holder category</th>
            <th style={TH}>Shares</th>
            <th style={TH}>Ownership</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(cap.by_category).map(([cat, shares]) => (
            <tr key={cat}>
              <td style={{ ...TD, textAlign: "left", textTransform: "capitalize" }}>{cat}</td>
              <td className="tnum" style={TD}>
                {countIn(shares)}
              </td>
              <td className="tnum" style={TD}>
                {pctText(cap.pct[cat] ?? 0)}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td style={{ ...TD, textAlign: "left", borderBottom: "none" }}>Total</td>
            <td className="tnum" style={{ ...TD, borderBottom: "none" }}>
              {countIn(cap.total_shares)}
            </td>
            <td className="tnum" style={{ ...TD, borderBottom: "none" }}>
              100.0%
            </td>
          </tr>
        </tfoot>
      </table>
      <div
        style={{
          borderTop: "1px solid var(--color-border)",
          padding: "8px 12px",
          fontSize: 12,
          color: "var(--color-ink-muted)",
        }}
      >
        {esop > 0 ? (
          <>
            ESOP pool: <span className="tnum">{countIn(esop)}</span> shares (
            <span className="tnum">{pctText(cap.pct["esop"] ?? 0)}</span> of issued).
          </>
        ) : (
          "No ESOP pool on record."
        )}{" "}
        SAFE / convertible notes have no stored register endpoint yet — conversions are computed
        on demand below from a note's own terms; nothing here is a stored balance.
      </div>
    </div>
  );
}

export function SafeOutcome({ result }: { result: { conversion_price_paise: number; shares_issued: number } }) {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
      <VerifiedNumber
        label="Conversion price / share"
        value={inr(result.conversion_price_paise)}
        state="honest_pending"
        note="Computed from the note terms entered above (cap vs discount, whichever is lower) — not a book figure."
      />
      <VerifiedNumber
        label="Shares issued on conversion"
        value={countIn(result.shares_issued)}
        state="honest_pending"
        note="Computed from the note terms entered above — not a book figure."
      />
    </div>
  );
}

export function InvestorPreviewCard({ upd }: { upd: InvestorPreviewData }) {
  return (
    <div
      style={{
        border: "1px solid var(--color-border)",
        background: "var(--color-surface)",
        borderRadius: 8,
        padding: "14px 16px",
      }}
    >
      <div style={{ fontSize: 12, color: "var(--color-ink-muted)", marginBottom: 8 }}>
        Update for <span className="tnum">{upd.period}</span>
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {upd.figures.map((f) => (
          <VerifiedNumber
            key={f.key}
            label={f.label}
            value={figureValue(f)}
            state={toVerifyState(f.state)}
            working={{ inputs: [{ label: "Fact key", value: f.key }] }}
          />
        ))}
        {/* Runway through the EXISTING WS7-E2E logic, verbatim — an empty ledger says so,
            an ambiguous null says "not yet known", never a flattering "∞". */}
        <VerifiedNumber
          label="Runway"
          value={runwayText({ runway_months: upd.runway_months, accounts: upd.accounts })}
          state="honest_pending"
          note="Runway is derived from the burn above; Mahsa has not recomputed it."
        />
      </div>
      <div style={{ fontSize: 13, marginTop: 12 }}>
        <div
          style={{
            fontSize: 10,
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            color: "var(--color-ink-faint)",
          }}
        >
          Cap table
        </div>
        {upd.cap_table.total_shares === 0 ? (
          <span style={{ color: "var(--color-ink-muted)" }}>
            No shareholders on record — the update will say so rather than show a split.
          </span>
        ) : (
          <span className="tnum">
            {countIn(upd.cap_table.total_shares)} shares ·{" "}
            {Object.entries(upd.cap_table.ownership)
              .map(([cat, frac]) => `${cat} ${pctText(frac)}`)
              .join(" · ")}
          </span>
        )}
      </div>
      {upd.highlights.length > 0 && (
        <ul style={{ fontSize: 13, margin: "10px 0 0", paddingLeft: 18 }}>
          {upd.highlights.map((h, i) => (
            <li key={i}>{h}</li>
          ))}
        </ul>
      )}
      <div style={{ fontSize: 12, color: "var(--color-ink-muted)", marginTop: 12 }}>
        Nothing is sent from this page. Sending uses the existing email surface —{" "}
        <a href={upd.send_via} style={{ color: "var(--color-accent)" }}>
          open the send page
        </a>{" "}
        to review and dispatch this exact update.
      </div>
    </div>
  );
}

const TH: React.CSSProperties = {
  padding: "6px 12px",
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: "var(--color-ink-faint)",
  textAlign: "right",
  fontWeight: "normal",
};
const TD: React.CSSProperties = {
  padding: "6px 12px",
  borderBottom: "1px solid var(--color-border)",
  textAlign: "right",
  whiteSpace: "nowrap",
};

// ── hooked sections (untested directly, matching every other SPA screen) ─────

const FIELD: React.CSSProperties = {
  display: "block",
  marginTop: 4,
  padding: "6px 10px",
  borderRadius: 4,
  border: "1px solid var(--color-border-strong)",
  background: "var(--color-surface)",
  color: "var(--color-ink)",
  fontSize: 13,
  fontFamily: "inherit",
  width: 160,
};

function Label({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <label style={{ fontSize: 11, color: "var(--color-ink-faint)" }}>
      {text}
      {children}
    </label>
  );
}

function RunButton({ disabled, label }: { disabled: boolean; label: string }) {
  return (
    <button
      type="submit"
      disabled={disabled}
      style={{
        background: disabled ? "var(--color-surface-sunk)" : "var(--color-accent)",
        color: disabled ? "var(--color-ink-faint)" : "var(--color-on-accent)",
        border: "none",
        padding: "7px 14px",
        borderRadius: 4,
        fontSize: 13,
        cursor: disabled ? "default" : "pointer",
        fontFamily: "inherit",
        alignSelf: "flex-end",
      }}
    >
      {label}
    </button>
  );
}

function ScenarioSection() {
  const [f, setF] = useState({ opening_cash: "", base_revenue: "", base_cost: "", extra_cost: "0" });
  const [revenueMult, setRevenueMult] = useState("1.0");
  const [horizon, setHorizon] = useState("12");
  const traceId = useTraceId("cfo-scenario");

  const parsed = {
    opening_cash: parseRupees(f.opening_cash),
    base_revenue: parseRupees(f.base_revenue),
    base_cost: parseRupees(f.base_cost),
    extra_cost: parseRupees(f.extra_cost),
  };
  const valid = Object.values(parsed).every((v) => v !== null);
  const anyInput =
    (parsed.opening_cash ?? 0) > 0 || (parsed.base_revenue ?? 0) > 0 || (parsed.base_cost ?? 0) > 0;

  const run = useMutation({
    mutationFn: (body: object) =>
      api<ScenarioResultData>("/forecast/scenario", { method: "POST", body: JSON.stringify(body) }),
  });
  // Freeze what the shown result was computed FROM, so edits after a run can't relabel it.
  const [ranWith, setRanWith] = useState<{ anyInput: boolean; horizon: number } | null>(null);

  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF({ ...f, [k]: e.target.value });

  return (
    <section>
      <H2>Scenario runner</H2>
      <p style={{ fontSize: 13, color: "var(--color-ink-muted)", margin: "0 0 10px" }}>
        Model a revenue change and extra spend — see the runway impact. Amounts in ₹ per month.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!valid) return;
          setRanWith({ anyInput, horizon: Number(horizon) });
          run.mutate({
            opening_cash: parsed.opening_cash,
            base_revenue: parsed.base_revenue,
            base_cost: parsed.base_cost,
            horizon_months: Number(horizon),
            revenue_mult: Number(revenueMult),
            extra_cost: parsed.extra_cost,
          });
        }}
        style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}
      >
        <Label text="Opening cash (₹)">
          <input style={FIELD} inputMode="decimal" value={f.opening_cash} onChange={set("opening_cash")} />
        </Label>
        <Label text="Monthly revenue (₹)">
          <input style={FIELD} inputMode="decimal" value={f.base_revenue} onChange={set("base_revenue")} />
        </Label>
        <Label text="Monthly cost (₹)">
          <input style={FIELD} inputMode="decimal" value={f.base_cost} onChange={set("base_cost")} />
        </Label>
        <Label text="Revenue">
          <select style={FIELD} value={revenueMult} onChange={(e) => setRevenueMult(e.target.value)}>
            <option value="0.8">−20%</option>
            <option value="1.0">Base</option>
            <option value="1.2">+20%</option>
            <option value="1.5">+50%</option>
          </select>
        </Label>
        <Label text="Extra monthly cost (₹)">
          <input style={FIELD} inputMode="decimal" value={f.extra_cost} onChange={set("extra_cost")} />
        </Label>
        <Label text="Horizon">
          <select style={FIELD} value={horizon} onChange={(e) => setHorizon(e.target.value)}>
            <option value="6">6 months</option>
            <option value="12">12 months</option>
            <option value="24">24 months</option>
          </select>
        </Label>
        <RunButton disabled={!valid || run.isPending} label={run.isPending ? "Running…" : "Run scenario"} />
      </form>
      {!valid && (
        <p style={{ fontSize: 12, color: "var(--color-ink-muted)", margin: "6px 0 0" }}>
          Enter each amount as a non-negative number (0 is fine) to run.
        </p>
      )}
      {run.isError && <div style={{ marginTop: 12 }}><ErrorState error={run.error} traceId={traceId} onRetry={() => run.reset()} /></div>}
      {run.data && ranWith && (
        <ScenarioOutcome result={run.data} anyInput={ranWith.anyInput} horizonMonths={ranWith.horizon} />
      )}
    </section>
  );
}

function SafeSection() {
  const [f, setF] = useState({
    investment: "",
    valuation_cap: "",
    discount_pct: "0",
    round_price: "",
    pre_round_shares: "",
  });
  const traceId = useTraceId("cfo-safe");
  const investment = parseRupees(f.investment);
  const cap = f.valuation_cap.trim() === "" ? undefined : parseRupees(f.valuation_cap);
  const price = parseRupees(f.round_price);
  const discount = Number(f.discount_pct);
  const shares = Number(f.pre_round_shares);
  const valid =
    investment !== null &&
    investment > 0 &&
    cap !== null && // "" -> undefined is allowed; a typed-but-invalid cap is not
    (cap === undefined || cap > 0) &&
    price !== null &&
    price > 0 &&
    Number.isFinite(discount) &&
    discount >= 0 &&
    discount < 100 &&
    Number.isInteger(shares) &&
    shares > 0;

  const run = useMutation({
    mutationFn: (body: object) =>
      api<{ conversion_price_paise: number; shares_issued: number }>("/equity/safe/convert", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setF({ ...f, [k]: e.target.value });

  return (
    <section>
      <H2>SAFE / convertible conversion</H2>
      <p style={{ fontSize: 13, color: "var(--color-ink-muted)", margin: "0 0 10px" }}>
        Compute a note&apos;s conversion at a priced round (cap vs discount, whichever prices
        lower) — the existing equity engine does the math; nothing is written.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!valid) return;
          run.mutate({
            investment,
            valuation_cap: cap ?? null,
            discount_rate: discount / 100,
            round_price_per_share: price,
            pre_round_shares: shares,
          });
        }}
        style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}
      >
        <Label text="Investment (₹)">
          <input style={FIELD} inputMode="decimal" value={f.investment} onChange={set("investment")} />
        </Label>
        <Label text="Valuation cap (₹, blank = none)">
          <input style={FIELD} inputMode="decimal" value={f.valuation_cap} onChange={set("valuation_cap")} />
        </Label>
        <Label text="Discount %">
          <input style={FIELD} inputMode="decimal" value={f.discount_pct} onChange={set("discount_pct")} />
        </Label>
        <Label text="Round price / share (₹)">
          <input style={FIELD} inputMode="decimal" value={f.round_price} onChange={set("round_price")} />
        </Label>
        <Label text="Pre-round shares">
          <input style={FIELD} inputMode="numeric" value={f.pre_round_shares} onChange={set("pre_round_shares")} />
        </Label>
        <RunButton disabled={!valid || run.isPending} label={run.isPending ? "Computing…" : "Compute conversion"} />
      </form>
      {run.isError && <div style={{ marginTop: 12 }}><ErrorState error={run.error} traceId={traceId} onRetry={() => run.reset()} /></div>}
      {run.data && <SafeOutcome result={run.data} />}
    </section>
  );
}

function CapTableSection() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["cap-table"],
    queryFn: () => api<CapTableData>("/equity/cap-table"),
  });
  const traceId = useTraceId("cfo-captable");
  return (
    <section>
      <H2>Cap table</H2>
      {isLoading && !data && <p style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>Loading…</p>}
      {error ? <ErrorState error={error} traceId={traceId} onRetry={refetch} /> : data && <CapTablePanel cap={data} />}
    </section>
  );
}

function InvestorSection() {
  const [draft, setDraft] = useState("");
  const [highlights, setHighlights] = useState<string[]>([]);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["investor-preview", highlights],
    queryFn: () =>
      api<InvestorPreviewData>("/investor/preview", {
        method: "POST",
        body: JSON.stringify({ highlights }),
      }),
  });
  const traceId = useTraceId("cfo-investor");
  return (
    <section>
      <H2>Investor update</H2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setHighlights(draft.split("\n").map((l) => l.trim()).filter(Boolean));
        }}
        style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 12 }}
      >
        <Label text="Highlights — one per line (optional)">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={3}
            style={{ ...FIELD, width: 420, maxWidth: "100%", resize: "vertical" }}
          />
        </Label>
        <RunButton disabled={isLoading} label="Rebuild preview" />
      </form>
      {isLoading && !data && <p style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>Loading…</p>}
      {error ? (
        <ErrorState error={error} traceId={traceId} onRetry={refetch} />
      ) : (
        data && <InvestorPreviewCard upd={data} />
      )}
    </section>
  );
}

export function Cfo() {
  return (
    <section>
      <Header title="CFO strategy" />
      <ScenarioSection />
      <CapTableSection />
      <SafeSection />
      <InvestorSection />
    </section>
  );
}
