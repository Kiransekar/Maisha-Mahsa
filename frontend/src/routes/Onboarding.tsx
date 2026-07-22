// First-run onboarding (WS7.8): GSTIN -> bank CSV -> the first figure. Target: under 15 minutes
// to the payoff moment (research T8 + anti-pattern #8 — a migration that stalls or paywalls a step
// is the top complaint; Zoho's stuck-2-months wizard is the thing NOT to build).
//
// Every step is honest about its own state:
//   · step 1 (GSTIN) is pure client-side format validation — there is no endpoint yet to prefill
//     or persist a filer GSTIN (grep confirms no route reads/writes `settings.company_gstin`),
//     so this step says exactly that instead of faking a prefill. See wiring_needed in the ticket.
//   · step 2 (bank) reuses the REAL treasury endpoints (POST /api/treasury/accounts, POST
//     /api/treasury/accounts/{id}/import) — no bespoke onboarding-only backend.
//   · step 3 is the payoff: GET /api/domains/treasury, the SAME assembler the Treasury hub page
//     renders, so the state shown here is not a special onboarding-only fabrication.
//
// PREVIEW-THEN-CONFIRM (T3 / invariant 4). `treasury.service.import_csv` inserts N
// bank_transactions AND rewrites `account.current_balance` — a bulk mutation. The endpoint has NO
// dry-run mode (router.import_statement always commits), so the dry run is done here: the selected
// file is parsed with a MIRROR of the server's parser (_HEADER_MAP / _DATE_FORMATS / _parse_amount
// below are ported field-for-field) and the row count, date range and ₹ totals are shown BEFORE
// anything is POSTed. The confirm then uploads the exact bytes that were previewed — the parsed
// text is held in state, so swapping the file on disk between preview and confirm cannot change
// what commits. After the write, the server's own counts are reconciled against the preview and
// any divergence is stated rather than hidden.
// A server-side `?dry_run=true` on the import route would be the better fix — see the report.
//
// A step that fails shows the server's real message and stays on that step (retry-safe) — never
// silently resets progress, never a blank panel (invariant 7, reusing ErrorState like Inbox.tsx).

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { inr } from "../lib/money";
import { useTraceId } from "../lib/trace";
import { VerifiedNumber, type VerifyState } from "../components/VerifiedNumber";
import { ErrorState } from "../components/ErrorState";
import { Header, H2, Empty, MahsaDownBanner } from "./Today";
import { honestState, type DomainData, type Figure } from "./Domain";

// The same seam as lib/api.ts. Duplicated as one line because `BASE` is not exported there and
// lib/api.ts is out of this ticket's file ownership — the multipart upload below cannot use
// `api()` (it must not send a JSON content-type). See the report: export BASE and this goes away.
const BASE = import.meta.env.VITE_API_BASE ?? "";

// ---- pure logic (tested in Onboarding.test.ts) ----------------------------------------------

const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;

/** 15-char GSTIN format only — this is a format check, not a real GSTN lookup (none is wired). */
export function validateGstin(raw: string): { valid: boolean; error: string | null } {
  const v = raw.trim().toUpperCase();
  if (v === "") return { valid: false, error: "GSTIN is required." };
  if (v.length !== 15) return { valid: false, error: `Must be 15 characters — got ${v.length}.` };
  if (!GSTIN_RE.test(v)) return { valid: false, error: "Doesn't match the GSTIN format." };
  return { valid: true, error: null };
}

/** Rupees (as typed) -> integer paise. Blank = 0 (opening balance is optional). Invalid input
 * returns null rather than silently defaulting to 0 — a typo should not become a fabricated
 * opening balance (invariant 4: no invented rupee value). */
export function rupeesToPaise(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return 0;
  const n = Number(trimmed);
  if (!Number.isFinite(n) || n < 0) return null;
  return Math.round(n * 100);
}

/** ₹ with the exact paise remainder spelled out. `inr()` rounds to whole rupees, which would
 * render a real 40-paise total as "₹0" — i.e. as nothing to import (invariant 2/8). */
export function inrPrecise(paise: number): string {
  const rem = Math.abs(paise) % 100;
  if (rem === 0) return inr(paise);
  return `${inr(paise - Math.sign(paise) * rem)} and ${rem} paise`;
}

// ---- CSV dry-run: a port of api/app/domains/treasury/service.py ------------------------------

const HEADER_MAP: [string, string[]][] = [
  ["date", ["transaction date", "tran date", "txn date", "value date", "date"]],
  ["description", ["narration", "transaction remarks", "particulars", "remarks", "description"]],
  ["reference", ["chq./ref.no.", "ref no", "cheque no", "chq/ref", "reference", "ref"]],
  ["debit", ["withdrawal amt", "withdrawal amount", "withdrawal", "debit", "dr"]],
  ["credit", ["deposit amt", "deposit amount", "deposit", "credit", "cr"]],
  ["balance", ["closing balance", "balance", "bal"]],
];

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

/** RFC4180-ish split, matching what Python's `csv.reader` does with the default dialect —
 * a naive `split(",")` would mis-column any narration containing a comma and the preview would
 * then not describe what the server is about to import. */
export function splitCsvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; } else quoted = false;
      } else cell += ch;
      continue;
    }
    if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(cell); cell = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else cell += ch;
  }
  if (cell !== "" || row.length > 0) { row.push(cell); rows.push(row); }
  // The server drops rows where every cell is blank before it even reads the header.
  return rows.filter((r) => r.some((c) => c.trim() !== ""));
}

/** Mirror of `_parse_date`: the seven formats the server accepts, else null (row is skipped). */
export function parseCsvDate(raw: string): string | null {
  const s = raw.trim();
  const two = (n: number) => String(n).padStart(2, "0");
  const build = (y: number, m: number, d: number) =>
    m >= 1 && m <= 12 && d >= 1 && d <= new Date(Date.UTC(y, m, 0)).getUTCDate()
      ? `${String(y).padStart(4, "0")}-${two(m)}-${two(d)}`
      : null;
  // Python's %y: 69-99 -> 19xx, 00-68 -> 20xx.
  const century = (yy: number) => (yy >= 69 ? 1900 + yy : 2000 + yy);

  // %Y needs four digits, but %m/%d accept an unpadded number — `strptime("2026-3-1")` parses.
  let m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(s);
  if (m) return build(+m[1], +m[2], +m[3]);
  m = /^(\d{1,2})[/-](\d{1,2})[/-](\d{2}|\d{4})$/.exec(s);
  if (m) return build(m[3].length === 2 ? century(+m[3]) : +m[3], +m[2], +m[1]);
  m = /^(\d{1,2})[- ]([A-Za-z]{3})[- ](\d{4})$/.exec(s);
  if (m) {
    const mi = MONTHS.indexOf(m[2].toLowerCase());
    return mi < 0 ? null : build(+m[3], mi + 1, +m[1]);
  }
  return null;
}

/** Mirror of `_parse_amount`: strip separators/symbols, anything unparsable is 0 (NOT an error —
 * the server does the same, which is exactly why a zero-amount row gets silently skipped). Exact
 * integer paise, computed on the digit string so no binary float touches money. */
export function parseCsvAmount(raw: string): number {
  const cleaned = raw.replace(/,/g, "").replace(/₹/g, "").replace(/Rs\./g, "").trim();
  if (["", "-", "0", "0.0", "0.00"].includes(cleaned)) return 0;
  // Decimal() also accepts exponent notation, so the mirror must too — otherwise a "1e3" cell
  // previews as 0 and imports as ₹1,000. ponytail: routed through float because the exponent form
  // never appears in a real statement; the plain-decimal path below stays exact integer math.
  if (/^[+-]?(\d+\.?\d*|\.\d+)[eE][+-]?\d+$/.test(cleaned)) return Math.round(Number(cleaned) * 100);
  const m = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(cleaned);
  if (!m || (m[2] === "" && !m[3])) return 0;
  const frac = (m[3] ?? "").padEnd(3, "0");
  const paise = Number(m[2] || "0") * 100 + Number(frac.slice(0, 2)) + (+frac[2] >= 5 ? 1 : 0);
  return m[1] === "-" ? -paise : paise;
}

export type PreviewRow = { date: string; description: string; debit: number; credit: number };
export type CsvPreview =
  | { ok: false; reason: string }
  | {
      ok: true;
      rows: PreviewRow[];
      skipped: number;
      debitPaise: number;
      creditPaise: number;
      from: string | null;
      to: string | null;
      /** True when the file carries its own balance column. `import_csv` OVERWRITES the running
       *  balance from that column (treasury/service.py:199-204), so credits-minus-debits is NOT
       *  the resulting balance and must not be asserted as one. */
      hasBalanceColumn: boolean;
      /** The last non-empty balance cell, i.e. what the server will actually end up recording. */
      statementClosingPaise: number | null;
    };

/** The dry run. Returns exactly the rows `import_csv` will insert, and the count it will drop. */
export function previewStatement(text: string): CsvPreview {
  const raw = splitCsvRows(text);
  if (raw.length === 0) return { ok: false, reason: "This file has no rows at all." };

  const header = raw[0].map((h) => h.trim().toLowerCase());
  const cols: Record<string, number> = {};
  for (const [field, candidates] of HEADER_MAP) {
    for (const cand of candidates) {
      const idx = header.findIndex((h) => h.includes(cand));
      if (idx !== -1) { cols[field] = idx; break; }
    }
  }
  if (!("date" in cols) || (!("debit" in cols) && !("credit" in cols))) {
    return {
      ok: false,
      reason: "unrecognised bank CSV: need a date column and a debit/credit column",
    };
  }

  const cell = (row: string[], field: string): string => {
    const i = cols[field];
    return i === undefined || i >= row.length ? "" : row[i].trim();
  };

  const rows: PreviewRow[] = [];
  let skipped = 0;
  let debitPaise = 0;
  let creditPaise = 0;
  const hasBalanceColumn = "balance" in cols;
  let statementClosingPaise: number | null = null;
  for (const r of raw.slice(1)) {
    const date = parseCsvDate(cell(r, "date"));
    if (date === null) { skipped++; continue; }
    const debit = parseCsvAmount(cell(r, "debit"));
    const credit = parseCsvAmount(cell(r, "credit"));
    if (debit === 0 && credit === 0) { skipped++; continue; }
    rows.push({ date, description: cell(r, "description"), debit, credit });
    debitPaise += debit;
    creditPaise += credit;
    // Mirror of service.py: a non-zero balance cell REPLACES the running balance.
    const bal = parseCsvAmount(cell(r, "balance"));
    if (hasBalanceColumn && bal !== 0) statementClosingPaise = bal;
  }
  const dates = rows.map((r) => r.date).sort();
  return {
    ok: true,
    rows,
    skipped,
    debitPaise,
    creditPaise,
    from: dates[0] ?? null,
    to: dates[dates.length - 1] ?? null,
    hasBalanceColumn,
    statementClosingPaise,
  };
}

/** The payoff figure: the first one Mahsa has actually recomputed, else the first honest one —
 * never an arbitrary pick that happens to look verified. */
export function pickFirstFigure(figures: Figure[], mahsaUp: boolean): Figure | null {
  if (figures.length === 0) return null;
  const verified = figures.find((f) => honestState(f.state, mahsaUp) === "verified");
  return verified ?? figures[0];
}

/** Step 3's heading must describe the figure that is ACTUALLY on screen. `pickFirstFigure` falls
 * back to an unverified figure when nothing is verified, and an unconditional "Your first verified
 * figure" would then assert a ✓ in larger type than the ◐ chip beside it can retract. */
export function figureHeading(state: VerifyState | null): string {
  if (state === "verified") return "Your first verified figure";
  if (state === "honest_pending") return "Your first figure — Mahsa hasn't sealed it yet";
  if (state === "unbacked") return "Your first figure — unbacked";
  return "Your first figure";
}

// ---- component ---------------------------------------------------------------------------

type Step = 1 | 2 | 3;

const STEP_LABEL: Record<Step, string> = {
  1: "GSTIN",
  2: "Bank statement",
  3: "First figure",
};

type ImportResult = {
  account_id: number;
  rows_imported: number;
  rows_skipped: number;
  closing_balance_paise: number;
};

export function Onboarding() {
  const [step, setStep] = useState<Step>(1);

  // Step 1 — pure client-side, nothing written yet.
  const [gstin, setGstin] = useState("");
  const gstinCheck = validateGstin(gstin);

  // Step 2 — real writes.
  const [bankName, setBankName] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [ifsc, setIfsc] = useState("");
  const [opening, setOpening] = useState("");
  const [accountId, setAccountId] = useState<number | null>(null);
  // The previewed bytes, held so the confirm uploads exactly what was shown (invariant 4).
  const [staged, setStaged] = useState<{ name: string; text: string; preview: CsvPreview } | null>(
    null,
  );
  const [imported, setImported] = useState<ImportResult | null>(null);
  const openingPaise = rupeesToPaise(opening);

  const accountTrace = useTraceId("onboarding-account");
  const importTrace = useTraceId("onboarding-import");
  const figureTrace = useTraceId("onboarding-figure");

  const createAccount = useMutation({
    mutationFn: (body: {
      bank_name: string;
      account_number: string;
      ifsc: string;
      opening_balance_paise: number;
    }) => api<{ id: number }>("/treasury/accounts", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (res) => setAccountId(res.id),
  });

  const importCsv = useMutation({
    mutationFn: async (vars: { accountId: number; name: string; text: string }) => {
      const form = new FormData();
      // Re-uploads the previewed text, not a fresh read of the File handle on disk.
      form.append("file", new Blob([vars.text], { type: "text/csv" }), vars.name);
      // Bypasses the shared `api()` helper's JSON content-type default — this is a multipart body —
      // but still goes through the VITE_API_BASE seam.
      const res = await fetch(`${BASE}/api/treasury/accounts/${vars.accountId}/import`, {
        method: "POST",
        credentials: "include",
        body: form,
      });
      if (!res.ok) throw new Error(await res.text().catch(() => `${res.status}`));
      return (await res.json()) as ImportResult;
    },
    onSuccess: setImported,
  });

  // Step 3 — the payoff, only fetched once a statement has actually been imported.
  const domainQuery = useQuery({
    queryKey: ["onboarding-treasury"],
    queryFn: () => api<DomainData>("/domains/treasury"),
    enabled: step === 3,
  });

  const submitBank = () => {
    if (!bankName || !accountNumber || !ifsc || openingPaise === null) return;
    createAccount.mutate({
      bank_name: bankName,
      account_number: accountNumber,
      ifsc,
      opening_balance_paise: openingPaise,
    });
  };

  const chooseFile = async (f: File | null) => {
    importCsv.reset();
    setImported(null);
    if (f === null) return setStaged(null);
    const text = await f.text();
    setStaged({ name: f.name, text, preview: previewStatement(text) });
  };

  // Only ever called from the confirm button under an OK preview with at least one row.
  const confirmImport = () => {
    if (accountId === null || staged === null || !staged.preview.ok) return;
    importCsv.mutate({ accountId, name: staged.name, text: staged.text });
  };

  const figure = domainQuery.data
    ? pickFirstFigure(domainQuery.data.figures, domainQuery.data.mahsa_up)
    : null;
  const figureState =
    figure && domainQuery.data ? honestState(figure.state, domainQuery.data.mahsa_up) : null;

  return (
    <section style={{ maxWidth: 620 }}>
      <Header title="Get started" />
      <div
        style={{
          display: "flex",
          gap: 8,
          marginBottom: 24,
          color: "var(--color-ink-muted)",
          fontSize: 12,
        }}
      >
        {([1, 2, 3] as Step[]).map((s) => (
          <span
            key={s}
            style={{
              padding: "4px 10px",
              borderRadius: 4,
              border: `1px solid ${
                s === step ? "var(--color-border-strong)" : "var(--color-border)"
              }`,
              background: s === step ? "var(--color-surface-sunk)" : "transparent",
              color: s === step ? "var(--color-ink)" : "var(--color-ink-muted)",
              fontWeight: 400,
            }}
          >
            {s}. {STEP_LABEL[s]}
          </span>
        ))}
      </div>

      {step === 1 && (
        <div>
          <H2>Your GSTIN</H2>
          <Empty>
            There is no lookup wired yet to prefill this — Maisha does not have a GSTN
            connection, so nothing here is guessed. Type your 15-character GSTIN below.
          </Empty>
          <input
            className="ident"
            value={gstin}
            onChange={(e) => setGstin(e.target.value.toUpperCase())}
            placeholder="22AAAAA0000A1Z5"
            maxLength={15}
            aria-label="GSTIN"
            style={{
              width: "100%",
              marginTop: 12,
              padding: "10px 12px",
              borderRadius: 4,
              border: "1px solid var(--color-border-strong)",
              background: "var(--color-surface)",
              color: "var(--color-ink)",
              fontSize: 14,
              fontWeight: 400,
            }}
          />
          {gstin && !gstinCheck.valid && (
            <div style={{ color: "var(--color-verify-unbacked)", fontSize: 12, marginTop: 6 }}>
              {gstinCheck.error}
            </div>
          )}
          <div style={{ color: "var(--color-ink-faint)", fontSize: 11, marginTop: 8 }}>
            This is held for this session only — there is no save endpoint for it yet
            (see wiring_needed).
          </div>
          <StepButtons onNext={() => setStep(2)} nextDisabled={!gstinCheck.valid} />
        </div>
      )}

      {step === 2 && (
        <div>
          <H2>Bank account</H2>
          {accountId === null ? (
            <>
              <Field label="Bank name" value={bankName} onChange={setBankName} />
              <Field label="Account number" value={accountNumber} onChange={setAccountNumber} />
              <Field label="IFSC" value={ifsc} onChange={setIfsc} mono />
              <Field
                label="Opening balance (₹, optional)"
                value={opening}
                onChange={setOpening}
                placeholder="0"
              />
              {opening && openingPaise === null && (
                <div style={{ color: "var(--color-verify-unbacked)", fontSize: 12 }}>
                  Not a valid amount.
                </div>
              )}
              {/* A failed account-create is a WRITE: the row may or may not have been committed
                  before the response failed, so read copy ("nothing was changed") would be a
                  claim we cannot make. `committed` is deliberately not passed — the server
                  reported no count, and we do not invent one. */}
              {createAccount.isError && (
                <ErrorState
                  error={createAccount.error}
                  traceId={accountTrace}
                  operation="write"
                  onRetry={() => createAccount.reset()}
                />
              )}
              <StepButtons
                onNext={submitBank}
                nextLabel={createAccount.isPending ? "Creating…" : "Create account"}
                nextDisabled={
                  !bankName || !accountNumber || !ifsc || openingPaise === null || createAccount.isPending
                }
                onBack={() => setStep(1)}
              />
            </>
          ) : imported ? (
            <ImportOutcome
              result={imported}
              preview={staged?.preview ?? null}
              onContinue={() => setStep(3)}
            />
          ) : (
            <>
              <div style={{ color: "var(--color-ink-muted)", fontSize: 13, marginBottom: 12 }}>
                Account created. Choose your bank statement CSV — you'll see exactly what it
                contains before anything is imported. Nothing is written until you confirm.
              </div>
              <input
                type="file"
                accept=".csv,text/csv"
                aria-label="Bank statement CSV"
                onChange={(e) => void chooseFile(e.target.files?.[0] ?? null)}
              />

              {staged && <StatementPreview name={staged.name} preview={staged.preview} />}

              {/* A failed import is a WRITE: import_csv inserts rows and rewrites the account
                  balance inside one transaction, and an HTTP-level failure tells us nothing about
                  whether it committed. No `committed` count — the server did not report one. */}
              {importCsv.isError && (
                <div style={{ marginTop: 12 }}>
                  <ErrorState
                    error={importCsv.error}
                    traceId={importTrace}
                    operation="write"
                    onRetry={() => importCsv.reset()}
                  />
                </div>
              )}
              <StepButtons
                onNext={confirmImport}
                nextLabel={
                  importCsv.isPending
                    ? "Importing…"
                    : staged?.preview.ok
                      ? `Import these ${staged.preview.rows.length} rows`
                      : "Import"
                }
                nextDisabled={
                  !staged?.preview.ok || staged.preview.rows.length === 0 || importCsv.isPending
                }
                onBack={() => setStep(1)}
              />
            </>
          )}
        </div>
      )}

      {step === 3 && (
        <div>
          <H2>{figureHeading(figureState)}</H2>
          {domainQuery.isLoading && (
            <p style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>Loading…</p>
          )}
          {domainQuery.error && (
            <ErrorState
              error={domainQuery.error}
              traceId={figureTrace}
              onRetry={() => void domainQuery.refetch()}
            />
          )}
          {domainQuery.data && !domainQuery.data.mahsa_up && <MahsaDownBanner />}
          {domainQuery.data && figure && figureState && (
            <>
              <VerifiedNumber
                label={figure.label}
                value={figure.value}
                state={figureState}
                asOf={domainQuery.data.as_of}
              />
              <div style={{ marginTop: 20 }}>
                <Link
                  to="/d/treasury"
                  style={{
                    color: "var(--color-accent)",
                    fontSize: 13,
                    textDecoration: "none",
                  }}
                >
                  Go to the Treasury hub →
                </Link>
              </div>
            </>
          )}
          {domainQuery.data && !figure && (
            <Empty>
              The import completed, but Treasury published no figures on this response. From here we
              can't tell whether they simply haven't been computed yet or whether no figure source
              is registered for this domain — so we won't assert either. Open the Treasury hub,
              which reads the same endpoint, or send us this reference:{" "}
              <span className="ident">{figureTrace}</span>.
            </Empty>
          )}
        </div>
      )}
    </section>
  );
}

/** The dry run, rendered. Everything here is derived from the selected file, nothing from a
 * server call — the copy says so, because a client-side parse is not a server dry-run. */
function StatementPreview({ name, preview }: { name: string; preview: CsvPreview }) {
  if (!preview.ok) {
    return (
      <div style={{ marginTop: 14 }}>
        <Empty>
          <strong style={{ fontWeight: 500 }}>{name}</strong> can't be imported as-is:{" "}
          {preview.reason} Nothing has been sent to the server. Export the statement again with a
          header row, or pick a different file.
        </Empty>
      </div>
    );
  }

  // Only the no-balance-column case lets us state a net effect: there, service.py accumulates
  // credits-minus-debits. With a balance column present it OVERWRITES the balance from the file,
  // so asserting a net effect would be an invented rupee figure (invariant 2).
  const net = preview.creditPaise - preview.debitPaise;
  return (
    <div
      style={{
        marginTop: 14,
        border: "1px solid var(--color-border-strong)",
        borderRadius: 8,
        padding: "14px 16px",
        background: "var(--color-surface)",
        fontSize: 13,
      }}
    >
      <div style={{ fontSize: 15, letterSpacing: "-0.01em", fontWeight: 400 }}>
        This is what will be imported
      </div>
      <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginTop: 2 }}>
        Read from <span className="ident">{name}</span> on this device. Nothing has been sent yet.
      </div>

      {preview.rows.length === 0 ? (
        <div style={{ marginTop: 12 }}>
          <Empty>
            No row in this file has both a readable date and a non-zero amount, so an import would
            insert nothing. The confirm button stays disabled.
          </Empty>
        </div>
      ) : (
        <dl style={{ margin: "12px 0 0", display: "grid", gap: 6 }}>
          <Stat label="Rows to import" value={`${preview.rows.length}`} />
          <Stat
            label="Date range"
            value={preview.from === preview.to ? `${preview.from}` : `${preview.from} → ${preview.to}`}
          />
          <Stat label="Total debits" value={inrPrecise(preview.debitPaise)} />
          <Stat label="Total credits" value={inrPrecise(preview.creditPaise)} />
          {preview.hasBalanceColumn ? (
            <>
              <Stat
                label="Closing balance the server will record"
                value={
                  preview.statementClosingPaise === null
                    ? "not yet known — we don't guess"
                    : inrPrecise(preview.statementClosingPaise)
                }
              />
              <div style={{ color: "var(--color-ink-faint)", fontSize: 11 }}>
                This file has its own balance column, so the import takes the closing balance from
                the statement itself rather than adding up the rows. Credits minus debits
                ({net >= 0 ? "+" : "−"}
                {inrPrecise(Math.abs(net))}) is shown above for reference only — it is not what the
                balance becomes.
              </div>
            </>
          ) : (
            <Stat
              label="Net effect on balance"
              value={`${net >= 0 ? "+" : "−"}${inrPrecise(Math.abs(net))}`}
            />
          )}
        </dl>
      )}

      {/* Skipped rows are a first-class result, not a footnote: a 340-line statement with 47
          unreadable rows produces a figure computed on partial data. */}
      {preview.skipped > 0 && (
        <div
          style={{
            marginTop: 12,
            border: "1px solid var(--color-warn)",
            borderRadius: 4,
            padding: "10px 12px",
            fontSize: 13,
          }}
        >
          <span className="tnum">{preview.skipped}</span> row(s) will be skipped — their date
          column couldn't be read, or both amount columns were zero. They will not appear in any
          figure computed after this import. Fix them in the CSV first if they matter.
        </div>
      )}

      {preview.rows.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--color-ink-muted)" }}>
            Show the first rows
          </summary>
          <div style={{ overflowX: "auto" }}>
            <table
              className="tnum"
              style={{ borderCollapse: "collapse", fontSize: 12, marginTop: 8, width: "100%" }}
            >
              <thead>
                <tr style={{ color: "var(--color-ink-muted)", textAlign: "left" }}>
                  <th style={TH}>Date</th>
                  <th style={TH}>Description</th>
                  <th style={{ ...TH, textAlign: "right" }}>Debit</th>
                  <th style={{ ...TH, textAlign: "right" }}>Credit</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.slice(0, 5).map((r, i) => (
                  <tr key={i}>
                    <td style={TD}>{r.date}</td>
                    <td style={{ ...TD, fontVariantNumeric: "normal" }}>{r.description || "—"}</td>
                    <td style={{ ...TD, textAlign: "right" }}>
                      {r.debit ? inrPrecise(r.debit) : "—"}
                    </td>
                    <td style={{ ...TD, textAlign: "right" }}>
                      {r.credit ? inrPrecise(r.credit) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {preview.rows.length > 5 && (
            <div style={{ color: "var(--color-ink-faint)", fontSize: 11, marginTop: 6 }}>
              Showing 5 of {preview.rows.length}. All {preview.rows.length} will be imported.
            </div>
          )}
        </details>
      )}
    </div>
  );
}

/** What the server actually did, reconciled against what was previewed. */
function ImportOutcome({
  result,
  preview,
  onContinue,
}: {
  result: ImportResult;
  preview: CsvPreview | null;
  onContinue: () => void;
}) {
  const expected = preview?.ok ? preview.rows.length : null;
  const drift = expected !== null && expected !== result.rows_imported;

  return (
    <div>
      <div
        style={{
          border: "1px solid var(--color-border-strong)",
          borderRadius: 8,
          padding: "14px 16px",
          background: "var(--color-surface)",
          fontSize: 13,
        }}
      >
        <div style={{ fontSize: 15, letterSpacing: "-0.01em", fontWeight: 400 }}>
          Statement imported
        </div>
        <dl style={{ margin: "12px 0 0", display: "grid", gap: 6 }}>
          <Stat label="Rows imported" value={`${result.rows_imported}`} />
          <Stat label="Rows skipped" value={`${result.rows_skipped}`} />
          <Stat
            label="Closing balance the server recorded"
            value={inrPrecise(result.closing_balance_paise)}
          />
        </dl>
        <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginTop: 10 }}>
          This closing balance is the server's arithmetic on the rows above. It has not been
          recomputed by Mahsa, so it carries no ✓ here.
        </div>
      </div>

      {result.rows_skipped > 0 && (
        <div
          style={{
            marginTop: 12,
            border: "1px solid var(--color-warn)",
            borderRadius: 4,
            padding: "10px 12px",
            fontSize: 13,
          }}
        >
          <span className="tnum">{result.rows_skipped}</span> row(s) in your file were skipped and
          are NOT in the balance above. Any figure you see next is computed on the{" "}
          <span className="tnum">{result.rows_imported}</span> rows that did import, not on the
          whole statement.
        </div>
      )}

      {drift && (
        <div
          style={{
            marginTop: 12,
            border: "1px solid var(--color-verify-unbacked)",
            borderRadius: 4,
            padding: "10px 12px",
            fontSize: 13,
          }}
        >
          The preview said <span className="tnum">{expected}</span> rows would import; the server
          imported <span className="tnum">{result.rows_imported}</span>. The two parsers disagree
          about this file. Check the imported transactions in the Treasury hub before you rely on
          the balance above.
        </div>
      )}

      <StepButtons onNext={onContinue} nextLabel="See your first figure" />
    </div>
  );
}

const TH: React.CSSProperties = {
  padding: "4px 10px 4px 0",
  borderBottom: "1px solid var(--color-border)",
  fontWeight: 400,
  whiteSpace: "nowrap",
};
const TD: React.CSSProperties = {
  padding: "4px 10px 4px 0",
  borderBottom: "1px solid var(--color-border)",
};

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
      <dt style={{ color: "var(--color-ink-muted)" }}>{label}</dt>
      <dd className="tnum" style={{ margin: 0 }}>
        {value}
      </dd>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  mono,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  mono?: boolean;
}) {
  return (
    <div style={{ marginBottom: 12 }}>
      <label style={{ display: "block", fontSize: 12, color: "var(--color-ink-muted)", marginBottom: 4 }}>
        {label}
        <input
          className={mono ? "ident" : undefined}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          style={{
            width: "100%",
            marginTop: 4,
            padding: "9px 12px",
            borderRadius: 4,
            border: "1px solid var(--color-border-strong)",
            background: "var(--color-surface)",
            color: "var(--color-ink)",
            fontSize: 14,
            fontWeight: 400,
          }}
        />
      </label>
    </div>
  );
}

function StepButtons({
  onNext,
  onBack,
  nextDisabled,
  nextLabel = "Next",
}: {
  onNext: () => void;
  onBack?: () => void;
  nextDisabled?: boolean;
  nextLabel?: string;
}) {
  return (
    <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
      {onBack && (
        <button
          onClick={onBack}
          style={{
            background: "transparent",
            border: "1px solid var(--color-border-strong)",
            color: "var(--color-ink)",
            padding: "8px 16px",
            borderRadius: 4,
            fontSize: 13,
            fontWeight: 400,
            fontFamily: "inherit",
            cursor: "pointer",
          }}
        >
          Back
        </button>
      )}
      <button
        onClick={onNext}
        disabled={nextDisabled}
        style={{
          background: "var(--color-accent)",
          color: "var(--color-on-accent)",
          border: "none",
          padding: "8px 16px",
          borderRadius: 4,
          fontSize: 13,
          fontWeight: 400,
          fontFamily: "inherit",
          cursor: nextDisabled ? "not-allowed" : "pointer",
          opacity: nextDisabled ? 0.5 : 1,
        }}
      >
        {nextLabel}
      </button>
    </div>
  );
}
