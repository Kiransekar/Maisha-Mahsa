// P1-5 — /statements: Trial Balance · P&L · Balance Sheet · General Ledger, read from the
// EXISTING ledger figures via /api/statements (app/web/api_statements.py — the api_domains
// assembler pattern, so every badge is server-decided, never invented here).
//
// Honesty rules (docs/WS7_BUILD_CONTRACT.md):
//   · Every money figure renders through VerifiedNumber with the payload's `state`; an
//     unrecognised state falls to ✕, never optimistically ✓ (T1).
//   · A broken book must LOOK broken: `balanced: false` on the trial balance or the balance-
//     sheet equation renders an explicit error banner — never silently absorbed (contract §2).
//   · Null money is "not yet known — we don't guess", never a fabricated figure (invariant 2).
//   · Printable: plain @media print CSS (theme/tokens.css) hides the shell + controls; the
//     tab bar and picker are `no-print`, the tables are just paper.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  VerifiedNumber,
  VerifyChip,
  type VerifyState,
} from "../components/VerifiedNumber";
import { ErrorState } from "../components/ErrorState";
import { api } from "../lib/api";
import { useTraceId } from "../lib/trace";
import { inrPrecise } from "../components/BankCsvImport";
import { Empty, Header } from "./Today";
import { Section } from "./Domain";

// ── types (the /api/statements wire contract) ────────────────────────────────

export type StmtFigure = {
  key: string;
  label: string;
  value: string;
  raw: number | null;
  state: string;
};

export type StatementsData = {
  as_of: string;
  trial_balance: { balanced: boolean; figures: StmtFigure[] };
  pnl: { figures: StmtFigure[] };
  balance_sheet: { balanced: boolean; figures: StmtFigure[] };
  accounts: { id: number; code: string; name: string; account_type: string }[];
};

export type GlLine = {
  date: string;
  description: string | null;
  debit: number;
  credit: number;
  balance: number;
};

export type GlData = {
  account_id: number;
  code: string;
  name: string;
  opening: StmtFigure;
  closing: StmtFigure;
  state: string;
  lines: GlLine[];
};

// ── pure logic (tested in Statements.test.tsx) ──────────────────────────────

const KNOWN_STATES = ["verified", "honest_pending", "unbacked"];

/** T1: the badge is the payload's, clamped — an unknown/missing state falls to ✕, never ✓. */
export function toVerifyState(state: string | null | undefined): VerifyState {
  return KNOWN_STATES.includes(state ?? "") ? (state as VerifyState) : "unbacked";
}

/** Invariant 2: a null money value states that it is unknown; it never renders as a figure. */
export const MONEY_UNKNOWN = "not yet known — we don't guess";

export function figureValue(f: Pick<StmtFigure, "raw" | "value">): string {
  return f.raw === null || f.raw === undefined ? MONEY_UNKNOWN : f.value;
}

/** The explicit broken-book banner copy. Flat declaratives; names the failed check. */
export function imbalanceMessage(kind: "tb" | "bs", diffValue?: string): string {
  if (kind === "tb") {
    const by = diffValue ? ` Debits and credits are off by ${diffValue}.` : "";
    return `Trial balance does not tie out.${by} These books are broken until the difference is found — do not file or report from them.`;
  }
  return "Balance sheet equation fails: assets do not equal liabilities + equity + retained profit. These books are broken — do not file or report from them.";
}

// ── presentational (pure; render-tested without a DOM) ──────────────────────

export function ImbalanceBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      style={{
        border: "1px solid var(--color-money-out)",
        color: "var(--color-money-out)",
        background: "var(--color-surface)",
        borderRadius: 8,
        padding: "12px 16px",
        fontSize: 13,
        margin: "0 0 10px",
      }}
    >
      {message}
    </div>
  );
}

function FigureRow({ figures, asOf }: { figures: StmtFigure[]; asOf?: string }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(232px, 1fr))",
        gap: 8, // dense interior — the working altitude's 8px rung
      }}
    >
      {figures.map((f) => (
        <VerifiedNumber
          key={f.key}
          label={f.label}
          value={figureValue(f)}
          state={toVerifyState(f.state)}
          asOf={asOf}
          working={{ inputs: [{ label: "Fact key", value: f.key }] }}
        />
      ))}
    </div>
  );
}

export function TrialBalancePanel({
  tb,
  asOf,
}: {
  tb: StatementsData["trial_balance"];
  asOf?: string;
}) {
  const diff = tb.figures.find((f) => f.key === "trial_balance_diff_paise");
  return (
    <div>
      {!tb.balanced && (
        <ImbalanceBanner message={imbalanceMessage("tb", diff ? figureValue(diff) : undefined)} />
      )}
      <FigureRow figures={tb.figures} asOf={asOf} />
    </div>
  );
}

export function PnlPanel({ pnl, asOf }: { pnl: StatementsData["pnl"]; asOf?: string }) {
  return <FigureRow figures={pnl.figures} asOf={asOf} />;
}

export function BalanceSheetPanel({
  bs,
  asOf,
}: {
  bs: StatementsData["balance_sheet"];
  asOf?: string;
}) {
  return (
    <div>
      {!bs.balanced && <ImbalanceBanner message={imbalanceMessage("bs")} />}
      <FigureRow figures={bs.figures} asOf={asOf} />
    </div>
  );
}

const CELL: React.CSSProperties = {
  padding: "5px 10px",
  borderBottom: "1px solid var(--color-border)",
  fontSize: 13,
  textAlign: "right",
  whiteSpace: "nowrap",
};
const CELL_L: React.CSSProperties = { ...CELL, textAlign: "left", whiteSpace: "normal" };

/** The account drilldown table: date-ordered postings with a running balance. Dense,
 *  Tally-grade; every ₹ through the canonical paise-exact renderer; the badge on the
 *  balance column is the PAYLOAD's state, rendered once in the header. */
export function GlTable({ gl }: { gl: GlData }) {
  const state = toVerifyState(gl.state);
  return (
    <div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
        <VerifiedNumber
          label={`Opening — ${gl.code} ${gl.name}`}
          value={figureValue(gl.opening)}
          state={toVerifyState(gl.opening.state)}
        />
        <VerifiedNumber
          label={`Closing — ${gl.code} ${gl.name}`}
          value={figureValue(gl.closing)}
          state={toVerifyState(gl.closing.state)}
        />
      </div>
      {gl.lines.length === 0 ? (
        <Empty>No posting has ever touched this account. That is an empty ledger, not ₹0 of activity.</Empty>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table
            className="tnum"
            style={{
              borderCollapse: "collapse",
              width: "100%",
              background: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: 4,
            }}
          >
            <thead>
              <tr style={{ background: "var(--color-surface-sunk)" }}>
                <th style={{ ...CELL_L, fontWeight: 500 }}>Date</th>
                <th style={{ ...CELL_L, fontWeight: 500 }}>Description</th>
                <th style={{ ...CELL, fontWeight: 500 }}>Debit</th>
                <th style={{ ...CELL, fontWeight: 500 }}>Credit</th>
                <th style={{ ...CELL, fontWeight: 500 }}>
                  Balance <VerifyChip state={state} />
                </th>
              </tr>
            </thead>
            <tbody>
              {gl.lines.map((ln, i) => (
                <tr key={i}>
                  <td style={CELL_L}>{ln.date}</td>
                  <td style={CELL_L}>{ln.description ?? "—"}</td>
                  <td style={CELL}>{ln.debit === 0 ? "—" : inrPrecise(ln.debit)}</td>
                  <td style={CELL}>{ln.credit === 0 ? "—" : inrPrecise(ln.credit)}</td>
                  <td style={CELL}>{inrPrecise(ln.balance)}</td>
                </tr>
              ))}
              {/* Totals row: tabular numerals; emphasis by background, not weight, so the
                  column never shifts (BRAND_THEME §4). */}
              <tr style={{ background: "var(--color-surface-sunk)" }}>
                <td style={CELL_L} colSpan={4}>
                  Closing balance
                </td>
                <td className="tnum" style={{ ...CELL, borderBottom: "none" }}>
                  {figureValue(gl.closing)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── screen ──────────────────────────────────────────────────────────────────

const TABS = [
  { key: "tb", label: "Trial Balance" },
  { key: "pnl", label: "Profit & Loss" },
  { key: "bs", label: "Balance Sheet" },
  { key: "gl", label: "General Ledger" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

export function Statements() {
  const [tab, setTab] = useState<TabKey>("tb");
  const traceId = useTraceId("statements");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["statements"],
    queryFn: () => api<StatementsData>("/statements"),
  });

  if (isLoading && !data) return <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>;

  if (error) {
    // Anti-pattern #14: never a blank shell — last-known statements render below, stale-marked.
    return (
      <div>
        <Header title="Statements" as_of={data?.as_of} />
        <ErrorState error={error} traceId={traceId} onRetry={refetch}>
          {data && (
            <>
              <Section>Last known — not current</Section>
              <TrialBalancePanel tb={data.trial_balance} asOf={data.as_of} />
            </>
          )}
        </ErrorState>
      </div>
    );
  }
  if (!data) return null;

  return (
    <section>
      <Header title="Statements" as_of={data.as_of} />
      <p style={{ fontSize: 12, color: "var(--color-ink-muted)", margin: "0 0 12px" }}>
        Read from the posted journal — the same figures the /api/ledger endpoints serve. No
        statement figure here is Mahsa-recomputed yet, which is why each reads ◐, not ✓.
      </p>

      <div className="no-print" role="tablist" style={{ display: "flex", gap: 4, marginBottom: 14, flexWrap: "wrap" }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            style={{
              padding: "7px 12px",
              borderRadius: 4,
              border: "1px solid var(--color-border-strong)",
              background: tab === t.key ? "var(--color-accent-sunk)" : "var(--color-surface)",
              color: tab === t.key ? "var(--color-accent)" : "var(--color-ink-muted)",
              fontSize: 13,
              cursor: "pointer",
              fontFamily: "inherit",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "tb" && (
        <>
          <Section>Trial balance · as of {data.as_of}</Section>
          <TrialBalancePanel tb={data.trial_balance} asOf={data.as_of} />
        </>
      )}
      {tab === "pnl" && (
        <>
          <Section>Profit &amp; loss · as of {data.as_of}</Section>
          <PnlPanel pnl={data.pnl} asOf={data.as_of} />
        </>
      )}
      {tab === "bs" && (
        <>
          <Section>Balance sheet · as of {data.as_of}</Section>
          <BalanceSheetPanel bs={data.balance_sheet} asOf={data.as_of} />
        </>
      )}
      {tab === "gl" && <GeneralLedgerTab accounts={data.accounts} />}
    </section>
  );
}

/** Account picker → drilldown. Native <select> on purpose (the OrgSwitcher precedent):
 *  correctness lives in the fetch, not in bespoke picker chrome. */
function GeneralLedgerTab({ accounts }: { accounts: StatementsData["accounts"] }) {
  const [accountId, setAccountId] = useState<number | null>(null);
  const traceId = useTraceId("statements-gl");
  const glQuery = useQuery({
    queryKey: ["statements-gl", accountId],
    queryFn: () => api<GlData>(`/statements/gl/${accountId}`),
    enabled: accountId !== null,
  });

  if (accounts.length === 0) {
    return (
      <Empty>
        No account exists in the chart of accounts yet, so there is no ledger to drill into.
        That is an unwired book, not an empty one.
      </Empty>
    );
  }

  return (
    <div>
      <Section>General ledger — account drilldown</Section>
      <label
        className="no-print"
        style={{ display: "block", fontSize: 12, color: "var(--color-ink-muted)", marginBottom: 10 }}
      >
        Account
        <select
          value={accountId ?? ""}
          onChange={(e) => setAccountId(e.target.value === "" ? null : Number(e.target.value))}
          style={{
            display: "block",
            marginTop: 4,
            padding: "6px 10px",
            borderRadius: 4,
            border: "1px solid var(--color-border-strong)",
            background: "var(--color-surface)",
            color: "var(--color-ink)",
            fontSize: 13,
            fontFamily: "inherit",
            minWidth: 260,
          }}
        >
          <option value="">Pick an account…</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.code} · {a.name} ({a.account_type})
            </option>
          ))}
        </select>
      </label>

      {accountId === null && (
        <Empty>Pick an account above to see every posting with its running balance.</Empty>
      )}
      {accountId !== null && glQuery.isLoading && (
        <p style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>Loading ledger…</p>
      )}
      {accountId !== null && glQuery.error != null && (
        <ErrorState
          error={glQuery.error}
          traceId={traceId}
          onRetry={() => void glQuery.refetch()}
        />
      )}
      {glQuery.data && <GlTable gl={glQuery.data} />}
    </div>
  );
}
