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
//   · Actions are fireable through the P0-2 preview→confirm machinery (api/app/web/api_actions.py):
//     the ActionDrawer holds no path to a commit without a server preview token, and the server
//     independently 409s a commit whose values were never previewed (invariant 9, both sides).

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { authHeaders } from "../lib/auth";
import {
  VerifiedNumber,
  effectiveState,
  isRestricted,
  LockChip,
  type Freshness,
  type RestrictedField,
  type VerifyState,
} from "../components/VerifiedNumber";
import { ErrorState } from "../components/ErrorState";
import { ActionDrawer } from "../components/ActionDrawer";
import { Sparkline } from "../components/Sparkline";
import { GstDetail } from "./GstDetail";
import { BankCsvImport } from "../components/BankCsvImport";
import { TallyEmpty, TallyImport } from "../components/TallyImport";
import { useConnectionHealth } from "../components/ConnectionHealth";
import { booksFreshness, useNow } from "../lib/freshness";
import { useTraceId } from "../lib/trace";
import { Empty, Header, MahsaDownBanner } from "./Today";

// Same seam as lib/api.ts / BankCsvImport.tsx — a multipart body must not carry the shared
// `api()` helper's JSON content-type, so the receipt upload below bypasses it directly.
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

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

export type FieldSpec = {
  name: string;
  label: string;
  type: string;
  required: boolean;
  placeholder: string;
  options: string[];
  /** P0-3: sub-schema for `type === "lines"` — a multi-row array field (invoice items,
   *  journal lines). Absent on scalar fields. */
  columns?: FieldSpec[];
};

export type ActionSpec = {
  key: string;
  label: string;
  fields: FieldSpec[];
};

export type AccountSummary = {
  id: number;
  bank_name: string;
  account_number: string;
  current_balance_paise: number;
};

export type DomainData = {
  domain: string;
  as_of: string;
  mahsa_up: boolean;
  mahsa_down_message: string | null;
  health: { status: string; score: number | null; requires_approval: boolean } | null;
  // T11: a sensitive figure arrives as a RestrictedField — the server stripped the value.
  figures: (Figure | RestrictedField)[];
  deadlines: Deadline[];
  actions: ActionSpec[];
};

// P2-3: GET /api/domains/{domain}/history — the SAME honest ≥2-point rule as the HTMX
// sparklines (app/web/charts.py): a metric with fewer than two real captures is simply absent
// from `series`, never a fabricated single-point or flat line.
export type HistoryPoint = { captured_at: string; value: number };
export type DomainHistory = { domain: string; series: Record<string, HistoryPoint[]> };

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

// P1-8 — expense receipt OCR. `/api/expense/ocr-receipt` returns this shape (mirrors
// `expense_calc.parse_receipt`); OCR is never authoritative, so every field it yields only ever
// PREFILLS an editable ActionDrawer field, same preview-then-confirm gate as manual entry.
export type ReceiptOcrResult = {
  amount_paise: number | null;
  gstin: string | null;
  date: string | null;
};

/** The server's date regex accepts a bare ISO date OR `DD/MM/YYYY`/`DD-MM-YYYY` (day-first,
 *  the Indian convention `expense_calc._DATE_RE` was written against). A bare ISO date is
 *  trusted as-is; the day-first form is reordered into ISO for the `<input type="date">`
 *  field. Anything else (or nothing found) leaves the date field for the user to fill in —
 *  guessing a US month/day swap would be worse than an honest blank. */
export function receiptDateToIso(raw: string | null): string {
  if (!raw) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  const m = /^(\d{2})[/-](\d{2})[/-](\d{4})$/.exec(raw);
  return m ? `${m[3]}-${m[2]}-${m[1]}` : "";
}

/** OCR result -> the `submit-claim` action's prefill map. `mergedInitialValues` (ActionDrawer)
 *  only ever applies keys the action's own schema declares, so a field this doesn't set (or a
 *  future schema without `vendor_gstin`) just stays blank rather than injecting anything. */
export function ocrResultToPrefill(r: ReceiptOcrResult): Record<string, string> {
  const prefill: Record<string, string> = {};
  const iso = receiptDateToIso(r.date);
  if (iso) prefill.expense_date = iso;
  if (typeof r.amount_paise === "number") prefill.amount = (r.amount_paise / 100).toString();
  if (r.gstin) prefill.vendor_gstin = r.gstin;
  return prefill;
}

// The ₹ half of the alert grammar. `/api/domains/{d}` ships the raw compliance calendar, which
// carries no penalty amount (unlike `/api/today`, which joins `ComplianceCalendar.penalty_amount`
// and the ported GSTR-3B late fee). Invariant 2: we say so, we do not print ₹0.
export const IMPACT_UNKNOWN = "₹ impact not yet known — we don't guess";

// ── screen ───────────────────────────────────────────────────────────────────

export function Domain() {
  const { domain = "" } = useParams();
  const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["domain", domain],
    queryFn: () => api<DomainData>(`/domains/${encodeURIComponent(domain)}`),
  });
  const traceId = useTraceId(`domain-${domain}`);
  // T4: `honestState` already downgrades a ✓ when Mahsa itself is unreachable; this ADDS the
  // real connection-health/payload-age check (same one Approvals wires) so a ✓ here also can't
  // survive on inputs the sources behind them never confirmed are current.
  const health = useConnectionHealth();
  const now = useNow();
  const age = dataUpdatedAt ? now - dataUpdatedAt : 0;
  const fresh = booksFreshness(health.data, age);

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

  return <DomainBody data={data} refetch={refetch} stale={fresh.stale} />;
}

/** Split out so the receipt-OCR prefill state (expense-only) doesn't have to be threaded
 *  through the loading/error early-returns above. */
function DomainBody({
  data,
  refetch,
  stale,
}: {
  data: DomainData;
  refetch: () => void;
  stale: Freshness;
}) {
  // P1-8: the most recent receipt parse, and a nonce that forces the submit-claim ActionDrawer
  // to remount (fresh prefill, fresh preview state) each time a new photo is read — same
  // "key changes -> component resets" pattern TreasuryReimport uses for its account picker.
  const [receiptPrefill, setReceiptPrefill] = useState<Record<string, string> | undefined>();
  const [receiptNonce, setReceiptNonce] = useState(0);

  // P2-3: trend sparklines, fetched separately so a slow/failed history read never blocks the
  // figures themselves rendering — `historyQuery.data` simply stays undefined and every card
  // renders with no spark (Sparkline's own ≥2-point guard would drop it anyway).
  const historyQuery = useQuery({
    queryKey: ["domain-history", data.domain],
    queryFn: () => api<DomainHistory>(`/domains/${encodeURIComponent(data.domain)}/history`),
  });

  const verified = data.figures.filter(
    (f) => !isRestricted(f) && honestState(f.state, data.mahsa_up) === "verified",
  );

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
          <FigureGrid
            figures={data.figures}
            mahsaUp={data.mahsa_up}
            asOf={data.as_of}
            stale={stale}
            history={historyQuery.data?.series}
          />
        </>
      )}

      {/* P2-2: GST deep flows (ITC recon, artifacts, IMS, QRMP/CMP-08 visibility). The badge
          gate is the SAME honestState wiring every other badge on this screen passes through. */}
      {data.domain === "gst" && <GstDetail badge={(s) => honestState(s, data.mahsa_up)} />}

      {/* P0-5: re-import reuses the SAME dry-run -> confirm component Onboarding's first
          statement uses (components/BankCsvImport.tsx) — no second parser, no second preview.
          Treasury-only: no other domain has a bank-account concept to import into. */}
      {data.domain === "treasury" && (
        <>
          <Section>Re-import bank statement</Section>
          <TreasuryReimport onImported={() => void refetch()} />
        </>
      )}

      {/* WS9.1: Tally XML import — the SAME parse-report -> mapping -> typed-confirm component
          Onboarding's Tally step uses (components/TallyImport.tsx), so the flow cannot fork.
          Ledger-only: the import writes chart-of-accounts + journal entries, nothing else. */}
      {data.domain === "ledger" && (
        <>
          <Section>Import from Tally</Section>
          <TallyEmpty />
          <div style={{ marginTop: 12 }}>
            <TallyImport traceNamespace="ledger-tally" onImported={() => void refetch()} />
          </div>
        </>
      )}

      {/* P2-1: vault browser — document list, full-text search, per-doc retention/integrity/
          clearance. Vault-only: no other domain has a document concept. The plain-text "Ingest
          document" ActionDrawer below (Actions section) is untouched — this adds browsing +
          the OCR-scan path alongside it. */}
      {data.domain === "vault" && (
        <>
          <Section>Documents</Section>
          <VaultBrowser />
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
            Every action is preview-then-confirm: you see exactly what will be created — with any
            ₹ echoed to the paisa — before anything is written. Enter advances fields;
            ⌘/Ctrl+Enter confirms from the preview.
          </p>
          {data.actions.map((a) => {
            // P1-8: the expense claim form additionally offers a receipt photo that prefills
            // it (GSTIN/amount/date) — every other action is untouched.
            const isClaimForm = data.domain === "expense" && a.key === "submit-claim";
            return (
              <div key={a.key}>
                {isClaimForm && (
                  <ExpenseReceiptCapture
                    onParsed={(prefill) => {
                      setReceiptPrefill(prefill);
                      setReceiptNonce((n) => n + 1);
                    }}
                  />
                )}
                <ActionDrawer
                  // Remounts on every new parse so the prefill + preview state starts fresh
                  // (same "key change resets the child" pattern as TreasuryReimport below).
                  key={isClaimForm ? `${a.key}-${receiptNonce}` : a.key}
                  domain={data.domain}
                  a={a}
                  // The one badge gate: preview figures pass through the same honestState as
                  // every other badge on this screen, so the drawer cannot invent its own path
                  // to a ✓.
                  badge={(s) => honestState(s, data.mahsa_up)}
                  onCommitted={() => void refetch()}
                  prefill={isClaimForm ? receiptPrefill : undefined}
                />
              </div>
            );
          })}
        </>
      )}
    </section>
  );
}

/** The account picker + the shared import component. A picker only appears with 2+ accounts
 *  (T2: chrome with exactly one choice is noise, matching the App.tsx OrgSwitcher precedent) —
 *  with exactly one account it is pre-selected, and with zero we point at onboarding rather than
 *  rendering a picker with nothing to pick. */
function TreasuryReimport({ onImported }: { onImported: () => void }) {
  const traceId = useTraceId("treasury-accounts");
  const accountsQuery = useQuery({
    queryKey: ["treasury-accounts"],
    queryFn: () => api<AccountSummary[]>("/treasury/accounts"),
  });
  const [selected, setSelected] = useState<number | null>(null);

  if (accountsQuery.isLoading) {
    return <p style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>Loading accounts…</p>;
  }
  if (accountsQuery.error) {
    return (
      <ErrorState
        error={accountsQuery.error}
        traceId={traceId}
        onRetry={() => void accountsQuery.refetch()}
      />
    );
  }
  const accounts = accountsQuery.data ?? [];
  if (accounts.length === 0) {
    return (
      <Empty>
        No bank account is on file yet, so there is nothing to re-import into.{" "}
        <Link to="/onboarding" style={{ color: "var(--color-accent)" }}>
          Add your first bank account →
        </Link>
      </Empty>
    );
  }
  const accountId = selected ?? accounts[0].id;

  return (
    <div>
      {accounts.length > 1 && (
        <label style={{ display: "block", fontSize: 12, color: "var(--color-ink-muted)", marginBottom: 10 }}>
          Account
          <select
            value={accountId}
            onChange={(e) => setSelected(Number(e.target.value))}
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
            }}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.bank_name} · {a.account_number}
              </option>
            ))}
          </select>
        </label>
      )}
      {/* Keyed on the account so switching accounts starts a fresh dry-run rather than
          carrying a staged preview from the previously selected account into a confirm. */}
      <BankCsvImport
        key={accountId}
        accountId={accountId}
        traceNamespace={`treasury-reimport-${accountId}`}
        onImported={onImported}
      />
    </div>
  );
}

// ── P2-1: vault browser (document list + full-text search + integrity/retention/clearance) ──
//
// GET /api/vault/search?q= is BOTH the search AND the document list: an empty `q` matches every
// document (vault_calc.search's substring check on ""), so no second "list all" endpoint exists
// or is needed. Results are already role-masked server-side (VaultService.browse, over the ONE
// canonical clearance lattice, app.core.landing.can_view_sensitivity) — a document above the
// caller's clearance still appears (existence is not a secret) as a locked row, never silently
// dropped and never with its content.

export type VaultDoc = {
  id: string;
  file_name: string;
  doc_type: string | null;
  sensitivity: string;
  retention_until: string | null;
  retention_overdue: boolean;
  restricted: boolean;
  reason?: string;
  tags?: string | null;
  /** Present only when `restricted` is false — SHA-256 verify state. Absent, never a guessed
   *  true, on a restricted row whose content this role never received. */
  integrity_ok?: boolean;
};

/** Honest-empty copy: "no results for this search" and "the vault is empty" are different facts
 *  and must not share a sentence. */
export function vaultEmptyText(query: string): string {
  return query.trim() === ""
    ? "No documents are in the vault yet."
    : `No document matches “${query.trim()}”.`;
}

/** The results list, given already-fetched hits — split out from the query-owning shell below
 *  so it renders (and is tested) without a network call, same pattern as `FigureGrid`. */
export function VaultResults({
  hits,
  query,
  highlightId,
}: {
  hits: VaultDoc[];
  query: string;
  /** CITE.P1-2: a `?doc=<sha>` deep-link from a citation's working panel — the matching
   *  document is highlighted; a missing match is stated honestly, never silently ignored. */
  highlightId?: string | null;
}) {
  const missingNote =
    highlightId && !hits.some((d) => d.id === highlightId)
      ? `The cited document (${highlightId.slice(0, 12)}…) is not in these results.`
      : null;
  if (hits.length === 0) return <Empty>{vaultEmptyText(query)}</Empty>;
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {missingNote && (
        <p style={{ fontSize: 12, color: "var(--color-warn)", margin: 0 }}>{missingNote}</p>
      )}
      {hits.map((d) => (
        <VaultDocRow key={d.id} doc={d} highlighted={d.id === highlightId} />
      ))}
    </div>
  );
}

function VaultDocRow({ doc, highlighted = false }: { doc: VaultDoc; highlighted?: boolean }) {
  const integrityFailed = !doc.restricted && doc.integrity_ok === false;
  return (
    <div
      style={{
        border: `1px solid ${
          integrityFailed
            ? "var(--color-verify-unbacked)"
            : highlighted
              ? "var(--color-accent)"
              : "var(--color-border)"
        }`,
        background: "var(--color-surface)",
        borderRadius: 6,
        padding: "8px 12px",
        fontSize: 13,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "baseline" }}>
        <strong style={{ fontWeight: 500 }}>{doc.file_name}</strong>
        {doc.restricted && <LockChip reason={doc.reason ?? "restricted"} />}
      </div>
      <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginTop: 2 }}>
        {doc.doc_type ?? "unclassified"} · {doc.sensitivity}
      </div>
      {highlighted && (
        <div style={{ color: "var(--color-accent)", fontSize: 12, marginTop: 2 }}>
          Cited source document — linked from a citation.
        </div>
      )}
      {!doc.restricted && (
        <div style={{ display: "flex", gap: 14, fontSize: 12, marginTop: 6, flexWrap: "wrap" }}>
          <span style={{ color: doc.integrity_ok ? "var(--color-verify)" : "var(--color-verify-unbacked)" }}>
            {doc.integrity_ok ? "✓ SHA-256 verified" : "✕ INTEGRITY CHECK FAILED"}
          </span>
          <span
            className="tnum"
            style={{ color: doc.retention_overdue ? "var(--color-warn)" : "var(--color-ink-faint)" }}
          >
            {doc.retention_until
              ? `retain until ${doc.retention_until}${doc.retention_overdue ? " — overdue for archival" : ""}`
              : "permanent record"}
          </span>
        </div>
      )}
      {/* LOUD: a content-hash mismatch is not a quiet ◐, it is its own alert. */}
      {integrityFailed && (
        <div
          style={{
            marginTop: 8,
            border: "1px solid var(--color-verify-unbacked)",
            borderRadius: 4,
            padding: "8px 10px",
            fontSize: 12,
            color: "var(--color-verify-unbacked)",
            fontWeight: 500,
          }}
        >
          This document's content no longer matches its recorded SHA-256 hash — it may have been
          altered outside the app. Do not rely on it until this is investigated.
        </div>
      )}
    </div>
  );
}

/** The query-owning shell: search box, OCR-scan capture, and the results list above. */
function VaultBrowser() {
  const [q, setQ] = useState("");
  // CITE.P1-2: `/d/vault?doc=<sha>` — the deep-link a citation's working panel emits
  // (app.core.anchors). The empty-q search lists every document, so the target is in the
  // result set (restricted docs still appear as locked rows) and gets highlighted.
  const [params] = useSearchParams();
  const linkedDocId = params.get("doc");
  const traceId = useTraceId("vault-search");
  const search = useQuery({
    queryKey: ["vault-search", q],
    queryFn: () => api<VaultDoc[]>(`/vault/search?q=${encodeURIComponent(q)}`),
  });

  return (
    <div>
      <input
        type="search"
        aria-label="Search vault documents"
        placeholder="Search file names, OCR text, tags…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        style={{
          display: "block",
          width: "100%",
          maxWidth: 420,
          padding: "7px 10px",
          borderRadius: 4,
          border: "1px solid var(--color-border-strong)",
          background: "var(--color-surface)",
          color: "var(--color-ink)",
          fontSize: 13,
          fontFamily: "inherit",
          marginBottom: 10,
        }}
      />
      <VaultOcrCapture onUploaded={() => void search.refetch()} />
      {search.isLoading ? (
        <p style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>Loading…</p>
      ) : search.error ? (
        <ErrorState error={search.error} traceId={traceId} onRetry={() => void search.refetch()} />
      ) : (
        <VaultResults hits={search.data ?? []} query={q} highlightId={linkedDocId} />
      )}
    </div>
  );
}

/** OCR-scan ingest — thin multipart POST to `/api/vault/ocr-ingest` (app/domains/vault/router.py),
 *  the SAME `VaultService.ingest_image` the pre-existing `/d/vault/ocr-ingest` HTMX route calls.
 *  Unlike the expense receipt capture (which only prefills a form), this ingest IS the write —
 *  it mirrors the shipped HTMX behaviour for this exact endpoint (content-hash dedup makes a
 *  re-scan idempotent, and nothing here touches money), so it commits directly rather than
 *  routing through the generic preview→confirm ActionDrawer. */
function VaultOcrCapture({ onUploaded }: { onUploaded: () => void }) {
  const traceId = useTraceId("vault-ocr-ingest");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function chooseFile(file: File | null) {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      form.append("upload_date", new Date().toISOString().slice(0, 10));
      const res = await fetch(`${API_BASE}/api/vault/ocr-ingest`, {
        method: "POST",
        credentials: "include",
        headers: await authHeaders(),
        body: form,
      });
      if (!res.ok) throw new Error(await res.text().catch(() => `${res.status}`));
      onUploaded();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        border: "1px solid var(--color-border)",
        background: "var(--color-surface)",
        borderRadius: 4,
        padding: "7px 12px",
        marginBottom: 10,
      }}
    >
      <label style={{ fontSize: 12, color: "var(--color-ink-muted)", display: "block" }}>
        Scan a document — OCR reads it straight into the vault, searchable immediately.
        <input
          type="file"
          accept="image/*"
          capture="environment"
          aria-label="Document photo"
          disabled={busy}
          onChange={(e) => void chooseFile(e.target.files?.[0] ?? null)}
          style={{ display: "block", marginTop: 4 }}
        />
      </label>
      {busy && (
        <p style={{ fontSize: 12, color: "var(--color-ink-faint)", margin: "6px 0 0" }}>
          Reading the document…
        </p>
      )}
      {error !== null && (
        <ErrorState error={error} traceId={traceId} operation="write" onRetry={() => setError(null)} />
      )}
    </div>
  );
}

/** P1-8 — receipt capture for the expense claim form. Uploads to `/api/expense/ocr-receipt`
 *  (a thin wrapper over the SAME `ExpenseService.ocr_capture` the HTMX drawer calls) and hands
 *  the parsed {amount_paise, gstin, date} up as an ActionDrawer prefill. OCR is never
 *  authoritative: nothing here writes a claim — it only fills in fields the user still reviews
 *  and confirms through the normal preview-then-confirm gate. */
function ExpenseReceiptCapture({
  onParsed,
}: {
  onParsed: (prefill: Record<string, string>) => void;
}) {
  const traceId = useTraceId("expense-receipt-ocr");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function chooseFile(file: File | null) {
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      const res = await fetch(`${API_BASE}/api/expense/ocr-receipt`, {
        method: "POST",
        credentials: "include",
        headers: await authHeaders(),
        body: form,
      });
      if (!res.ok) throw new Error(await res.text().catch(() => `${res.status}`));
      onParsed(ocrResultToPrefill((await res.json()) as ReceiptOcrResult));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        border: "1px solid var(--color-border)",
        background: "var(--color-surface)",
        borderRadius: 4,
        padding: "7px 12px",
        marginBottom: 4,
      }}
    >
      <label style={{ fontSize: 12, color: "var(--color-ink-muted)", display: "block" }}>
        Capture a receipt — GSTIN, amount and date are read off it into the form below, editable
        before you submit.
        <input
          type="file"
          accept="image/*"
          capture="environment"
          aria-label="Receipt photo"
          disabled={busy}
          onChange={(e) => void chooseFile(e.target.files?.[0] ?? null)}
          style={{ display: "block", marginTop: 4 }}
        />
      </label>
      {busy && (
        <p style={{ fontSize: 12, color: "var(--color-ink-faint)", margin: "6px 0 0" }}>
          Reading the receipt…
        </p>
      )}
      {error !== null && (
        <ErrorState error={error} traceId={traceId} operation="read" onRetry={() => setError(null)} />
      )}
    </div>
  );
}

/** P1-6 mutation guard: if a caller stops passing `stale` through here (or this stops forwarding
 *  it to VerifiedNumber), a figure keeps reading ✓ on sources nobody confirmed are current —
 *  see the "downgrades" tests in Domain.test.ts. */
export function FigureGrid({
  figures,
  mahsaUp,
  asOf,
  stale = false,
  history,
}: {
  figures: (Figure | RestrictedField)[];
  mahsaUp: boolean;
  asOf: string;
  stale?: Freshness;
  // P2-3: keyed by the SAME fact key the figure carries — absent (or <2 points) simply means
  // that card gets no `spark`, never a fabricated one (Sparkline enforces the ≥2 rule itself).
  history?: Record<string, HistoryPoint[]>;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(232px, 1fr))",
        gap: 8, // dense interior: the 8px rung, not Today's 12
      }}
    >
      {figures.map((f) =>
        // T11: a masked figure is a visible lock (label + server reason), never a blank slot
        // and never a VerifiedNumber (which would show a false ✕ on a value that exists).
        isRestricted(f) ? (
          <div
            key={f.key ?? f.label ?? "restricted"}
            style={{
              background: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              padding: "10px 12px",
            }}
          >
            <div style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>
              {f.label ?? "Restricted figure"}
            </div>
            <div style={{ marginTop: 8 }}>
              <LockChip reason={f.reason} />
            </div>
          </div>
        ) : (
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
            spark={<Sparkline values={(history?.[f.key] ?? []).map((p) => p.value)} />}
          />
        ),
      )}
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
