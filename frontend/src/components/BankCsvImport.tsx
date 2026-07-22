// P0-5 — the ONE bank-CSV dry-run -> confirm import, reused by Onboarding (first statement)
// and the treasury domain screen (re-import). Extracted from Onboarding.tsx so a second call
// site cannot fork the parser or the preview (the ticket's whole point) — everything that
// decides what a row previews as, or whether confirm is allowed, lives here once.
//
// PREVIEW-THEN-CONFIRM (T3 / invariant 9). `treasury.service.import_csv` inserts N
// bank_transactions AND rewrites `account.current_balance` — a bulk mutation, and the endpoint
// has NO dry-run mode (it always commits). So the dry run is done here: the selected file is
// parsed with a MIRROR of the server's parser (HEADER_MAP / DATE_FORMATS / parseCsvAmount below
// are ported field-for-field from api/app/domains/treasury/service.py) and the row count, date
// range and ₹ totals are shown BEFORE anything is POSTed. Confirm then uploads the exact bytes
// that were previewed — the parsed text is held in state, so swapping the file on disk between
// preview and confirm cannot change what commits. After the write, the server's own counts are
// reconciled against the preview and any divergence is stated rather than hidden.
//
// A step that fails shows the server's real message and offers retry — never a blank panel
// (invariant 7).

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { authHeaders } from "../lib/auth";
import { inr } from "../lib/money";
import { useTraceId } from "../lib/trace";
import { ErrorState } from "./ErrorState";
import { Empty } from "../routes/Today";

// Same seam as lib/api.ts. Duplicated as one line because `BASE` is not exported there and the
// multipart upload below cannot use `api()` (it must not send a JSON content-type).
const BASE = import.meta.env.VITE_API_BASE ?? "";

// ---- pure logic (tested in BankCsvImport.test.tsx) --------------------------------------------

const HEADER_MAP: [string, string[]][] = [
  ["date", ["transaction date", "tran date", "txn date", "value date", "date"]],
  ["description", ["narration", "transaction remarks", "particulars", "remarks", "description"]],
  ["reference", ["chq./ref.no.", "ref no", "cheque no", "chq/ref", "reference", "ref"]],
  ["debit", ["withdrawal amt", "withdrawal amount", "withdrawal", "debit", "dr"]],
  ["credit", ["deposit amt", "deposit amount", "deposit", "credit", "cr"]],
  ["balance", ["closing balance", "balance", "bal"]],
];

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

/** ₹ with the exact paise remainder spelled out. `inr()` rounds to whole rupees, which would
 * render a real 40-paise total as "₹0" — i.e. as nothing to import (invariant 2/8). */
export function inrPrecise(paise: number): string {
  const rem = Math.abs(paise) % 100;
  if (rem === 0) return inr(paise);
  return `${inr(paise - Math.sign(paise) * rem)} and ${rem} paise`;
}

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

/** The single gate the confirm button passes through, wherever it is rendered: never armed
 *  without an OK preview carrying at least one importable row, and never while a write is
 *  already in flight (invariant 9 — no double-submit is a silent second mutation). */
export function canConfirmImport(preview: CsvPreview | null, pending: boolean): boolean {
  return preview !== null && preview.ok && preview.rows.length > 0 && !pending;
}

export type ImportResult = {
  account_id: number;
  rows_imported: number;
  rows_skipped: number;
  closing_balance_paise: number;
};

// ---- component ----------------------------------------------------------------------------

/**
 * The whole dry-run -> confirm flow for one bank account. Self-contained: owns the staged file,
 * the preview, and the import mutation. A caller (Onboarding, the treasury domain screen) only
 * needs to give it an account to import into and learn when a statement lands.
 */
export function BankCsvImport({
  accountId,
  traceNamespace,
  onImported,
  footer,
}: {
  accountId: number;
  /** Namespace for `useTraceId`, so two mounted copies (onboarding vs. re-import) never collide. */
  traceNamespace: string;
  /** Fires once per successful import — callers refresh whatever figures depend on this account. */
  onImported?: (result: ImportResult) => void;
  /** Rendered below the outcome instead of the default "import another" reset. */
  footer?: (result: ImportResult) => React.ReactNode;
}) {
  const [staged, setStaged] = useState<{ name: string; text: string; preview: CsvPreview } | null>(
    null,
  );
  const [imported, setImported] = useState<ImportResult | null>(null);
  const importTrace = useTraceId(traceNamespace);

  const importCsv = useMutation({
    mutationFn: async (vars: { name: string; text: string }) => {
      const form = new FormData();
      // Re-uploads the previewed text, not a fresh read of the File handle on disk.
      form.append("file", new Blob([vars.text], { type: "text/csv" }), vars.name);
      // Bypasses the shared `api()` helper (a multipart body must not carry a JSON content-type)
      // but still attaches the same bearer token every other call gets, via the same `authHeaders`.
      const res = await fetch(`${BASE}/api/treasury/accounts/${accountId}/import`, {
        method: "POST",
        credentials: "include",
        headers: await authHeaders(),
        body: form,
      });
      if (!res.ok) throw new Error(await res.text().catch(() => `${res.status}`));
      return (await res.json()) as ImportResult;
    },
    onSuccess: (result) => {
      setImported(result);
      onImported?.(result);
    },
  });

  const chooseFile = async (f: File | null) => {
    importCsv.reset();
    setImported(null);
    if (f === null) return setStaged(null);
    const text = await f.text();
    setStaged({ name: f.name, text, preview: previewStatement(text) });
  };

  const confirmImport = () => {
    if (!canConfirmImport(staged?.preview ?? null, importCsv.isPending)) return;
    if (staged === null) return;
    importCsv.mutate({ name: staged.name, text: staged.text });
  };

  if (imported) {
    return (
      <div>
        <ImportOutcome result={imported} preview={staged?.preview ?? null} />
        {footer ? (
          footer(imported)
        ) : (
          <div style={{ marginTop: 14 }}>
            <button
              onClick={() => { setImported(null); setStaged(null); importCsv.reset(); }}
              style={RESET_BUTTON}
            >
              Import another statement
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <input
        type="file"
        accept=".csv,text/csv"
        aria-label="Bank statement CSV"
        onChange={(e) => void chooseFile(e.target.files?.[0] ?? null)}
      />

      {staged && <StatementPreview name={staged.name} preview={staged.preview} />}

      {/* A failed import is a WRITE: import_csv inserts rows and rewrites the account balance
          inside one transaction, and an HTTP-level failure tells us nothing about whether it
          committed. No `committed` count — the server did not report one. */}
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

      <div style={{ marginTop: 18 }}>
        <button
          onClick={confirmImport}
          disabled={!canConfirmImport(staged?.preview ?? null, importCsv.isPending)}
          style={{
            ...CONFIRM_BUTTON,
            cursor: canConfirmImport(staged?.preview ?? null, importCsv.isPending)
              ? "pointer"
              : "not-allowed",
            opacity: canConfirmImport(staged?.preview ?? null, importCsv.isPending) ? 1 : 0.5,
          }}
        >
          {importCsv.isPending
            ? "Importing…"
            : staged?.preview.ok
              ? `Import these ${staged.preview.rows.length} rows`
              : "Import"}
        </button>
      </div>
    </div>
  );
}

const CONFIRM_BUTTON: React.CSSProperties = {
  background: "var(--color-accent)",
  color: "var(--color-on-accent)",
  border: "none",
  padding: "8px 16px",
  borderRadius: 4,
  fontSize: 13,
  fontWeight: 400,
  fontFamily: "inherit",
};

const RESET_BUTTON: React.CSSProperties = {
  background: "transparent",
  border: "1px solid var(--color-border-strong)",
  color: "var(--color-ink)",
  padding: "8px 16px",
  borderRadius: 4,
  fontSize: 13,
  fontWeight: 400,
  fontFamily: "inherit",
  cursor: "pointer",
};

/** The dry run, rendered. Everything here is derived from the selected file, nothing from a
 * server call — the copy says so, because a client-side parse is not a server dry-run. */
export function StatementPreview({ name, preview }: { name: string; preview: CsvPreview }) {
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
export function ImportOutcome({
  result,
  preview,
}: {
  result: ImportResult;
  preview: CsvPreview | null;
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
