// WS9.1 — the ONE Tally XML import flow: upload -> server parse report (the reconciliation
// report) -> map unmatched ledgers -> typed CONFIRM. Reused by Onboarding (the Tally step) and
// the /d/ledger screen, so a second call site cannot fork the flow — same shape as
// BankCsvImport (P0-5), with one deliberate difference: the dry run here is the SERVER'S OWN
// parse (POST /parse mutates nothing, row-count asserted in api tests), not a client-side
// mirror parser. The report on screen is exactly what the commit path will re-validate.
//
// PREVIEW-THEN-CONFIRM (invariant 9): commit re-uploads the EXACT bytes that were parsed (held
// as an ArrayBuffer — never re-read from disk, and never decoded/re-encoded, since the token is
// an HMAC over the file's sha256), plus the mapping and the typed confirm word. A commit
// without a matching parse, or with a swapped file, is a 409 that writes nothing.
//
// Errors show the server's real message and offer retry — never a blank panel (invariant 7).

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { authHeaders } from "../lib/auth";
import { useTraceId } from "../lib/trace";
import { ErrorState } from "./ErrorState";
import { Empty } from "../routes/Today";
import { inrPrecise } from "./BankCsvImport";

// Same seam as BankCsvImport.tsx — multipart must not carry the shared JSON content-type.
const BASE = import.meta.env.VITE_API_BASE ?? "";

// ---- types mirroring app/web/api_tally.py responses -------------------------------------------

export type ReconRow = {
  name: string;
  opening_paise: number | null;
  debits_paise: number;
  credits_paise: number;
  computed_closing_paise: number;
  stated_closing_paise: number | null;
  match: boolean | null; // null = Tally stated no closing — unknown, never a fabricated pass
};

export type ParseReport = {
  committed: false;
  counts: { ledger_masters: number; vouchers: number; voucher_lines: number };
  errors: string[];
  unbalanced: { voucher_id: string; diff_paise: number }[];
  reconciliation: ReconRow[];
  matched: { name: string; account_id: number; code: string }[];
  unmatched: { name: string; parent: string | null; suggested_type: string | null }[];
  accounts: { id: number; code: string; name: string; account_type: string }[];
  file_sha256: string;
  preview_token: string;
  confirm_word: string;
};

export type CommitResult = {
  committed: true;
  accounts_created: { name: string; account_id: number; opening_paise: number }[];
  journals_posted: number;
  trial_balance: { total_debit: number; total_credit: number; diff: number; balanced: boolean };
};

/** One unmatched name's mapping choice. Matches the commit endpoint's JSON shape. */
export type MappingEntry =
  | { account_id: number }
  | { create: { code: string; name: string; account_type: string } };

export const ACCOUNT_TYPES = ["asset", "liability", "equity", "income", "expense"] as const;

// ---- pure logic (tested in TallyImport.test.tsx) ----------------------------------------------

/** Every unmatched ledger must be mapped — to an existing account or a complete create-new. */
export function mappingComplete(
  report: ParseReport,
  mapping: Record<string, MappingEntry | undefined>,
): boolean {
  return report.unmatched.every((u) => {
    const m = mapping[u.name];
    if (!m) return false;
    if ("account_id" in m) return Number.isInteger(m.account_id) && m.account_id > 0;
    return (
      m.create.code.trim() !== "" &&
      m.create.name.trim() !== "" &&
      (ACCOUNT_TYPES as readonly string[]).includes(m.create.account_type)
    );
  });
}

/** The single gate the confirm button passes through: a clean report (no exact-paise errors, no
 * unbalanced voucher, at least one voucher), a complete mapping, the typed confirm word, and no
 * write already in flight. */
export function canCommitTally(
  report: ParseReport | null,
  mapping: Record<string, MappingEntry | undefined>,
  confirmText: string,
  pending: boolean,
): boolean {
  return (
    report !== null &&
    report.errors.length === 0 &&
    report.unbalanced.length === 0 &&
    report.counts.vouchers > 0 &&
    mappingComplete(report, mapping) &&
    confirmText.trim().toLowerCase() === report.confirm_word &&
    !pending
  );
}

// ---- component --------------------------------------------------------------------------------

export function TallyImport({
  traceNamespace,
  onImported,
}: {
  traceNamespace: string;
  onImported?: (result: CommitResult) => void;
}) {
  const [staged, setStaged] = useState<{ name: string; bytes: ArrayBuffer } | null>(null);
  const [mapping, setMapping] = useState<Record<string, MappingEntry | undefined>>({});
  const [confirmText, setConfirmText] = useState("");
  const trace = useTraceId(traceNamespace);

  const upload = async (path: string, extra?: Record<string, string>) => {
    if (staged === null) throw new Error("no file staged");
    const form = new FormData();
    form.append("file", new Blob([staged.bytes], { type: "text/xml" }), staged.name);
    for (const [k, v] of Object.entries(extra ?? {})) form.append(k, v);
    const res = await fetch(`${BASE}${path}`, {
      method: "POST",
      credentials: "include",
      headers: await authHeaders(),
      body: form,
    });
    if (!res.ok) throw new Error(await res.text().catch(() => `${res.status}`));
    return res.json();
  };

  const parse = useMutation({
    mutationFn: () => upload("/api/ledger/tally/parse") as Promise<ParseReport>,
  });
  const commit = useMutation({
    mutationFn: (vars: { report: ParseReport }) =>
      upload("/api/ledger/tally/commit", {
        preview_token: vars.report.preview_token,
        confirm_text: confirmText.trim(),
        mapping: JSON.stringify(
          Object.fromEntries(Object.entries(mapping).filter(([, v]) => v !== undefined)),
        ),
      }) as Promise<CommitResult>,
    onSuccess: (result) => onImported?.(result),
  });

  const chooseFile = async (f: File | null) => {
    parse.reset();
    commit.reset();
    setMapping({});
    setConfirmText("");
    if (f === null) return setStaged(null);
    // The raw bytes, never decoded: the commit token binds sha256 of exactly these.
    const bytes = await f.arrayBuffer();
    setStaged({ name: f.name, bytes });
  };

  const report = parse.data ?? null;

  if (commit.data) {
    return (
      <div style={PANEL}>
        <div style={{ fontSize: 15, fontWeight: 400 }}>Tally books imported</div>
        <dl style={{ margin: "12px 0 0", display: "grid", gap: 6 }}>
          <Stat label="Journal entries posted" value={`${commit.data.journals_posted}`} />
          <Stat label="Accounts created" value={`${commit.data.accounts_created.length}`} />
          <Stat
            label="Trial balance"
            value={
              commit.data.trial_balance.balanced
                ? `ties out — ${inrPrecise(commit.data.trial_balance.total_debit)} each side`
                : `OFF by ${inrPrecise(commit.data.trial_balance.diff)}`
            }
          />
        </dl>
        <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginTop: 10 }}>
          These are the server's own post-commit totals. They have not been recomputed by Mahsa,
          so they carry no ✓ here — the ledger domain page shows the badged figures.
        </div>
      </div>
    );
  }

  return (
    <div>
      <input
        type="file"
        accept=".xml,text/xml,application/xml"
        aria-label="Tally XML export"
        onChange={(e) => void chooseFile(e.target.files?.[0] ?? null)}
      />
      {staged && !report && (
        <div style={{ marginTop: 12 }}>
          <button
            onClick={() => parse.mutate()}
            disabled={parse.isPending}
            style={BUTTON}
          >
            {parse.isPending ? "Parsing…" : `Parse ${staged.name}`}
          </button>
          <div style={{ color: "var(--color-ink-faint)", fontSize: 11, marginTop: 6 }}>
            Parsing reads the file and reports what it contains. Nothing is imported until you
            review the report and type the confirm word.
          </div>
        </div>
      )}

      {parse.isError && (
        <div style={{ marginTop: 12 }}>
          <ErrorState error={parse.error} traceId={trace} onRetry={() => parse.reset()} />
        </div>
      )}

      {report && (
        <TallyReport
          report={report}
          mapping={mapping}
          setMapping={setMapping}
          confirmText={confirmText}
          setConfirmText={setConfirmText}
        />
      )}

      {commit.isError && (
        <div style={{ marginTop: 12 }}>
          <ErrorState
            error={commit.error}
            traceId={trace}
            operation="write"
            onRetry={() => commit.reset()}
          />
        </div>
      )}

      {report && (
        <div style={{ marginTop: 18 }}>
          <button
            onClick={() => {
              if (!canCommitTally(report, mapping, confirmText, commit.isPending)) return;
              commit.mutate({ report });
            }}
            disabled={!canCommitTally(report, mapping, confirmText, commit.isPending)}
            style={{
              ...BUTTON,
              cursor: canCommitTally(report, mapping, confirmText, commit.isPending)
                ? "pointer"
                : "not-allowed",
              opacity: canCommitTally(report, mapping, confirmText, commit.isPending) ? 1 : 0.5,
            }}
          >
            {commit.isPending
              ? "Importing…"
              : `Import ${report.counts.vouchers} voucher(s) into the books`}
          </button>
        </div>
      )}
    </div>
  );
}

// ---- the reconciliation report, rendered ------------------------------------------------------

export function TallyReport({
  report,
  mapping,
  setMapping,
  confirmText,
  setConfirmText,
}: {
  report: ParseReport;
  mapping: Record<string, MappingEntry | undefined>;
  setMapping: (m: Record<string, MappingEntry | undefined>) => void;
  confirmText: string;
  setConfirmText: (v: string) => void;
}) {
  const mismatches = report.reconciliation.filter((r) => r.match === false);
  const unknown = report.reconciliation.filter((r) => r.match === null);
  const blocked = report.errors.length > 0 || report.unbalanced.length > 0;

  return (
    <div style={{ ...PANEL, marginTop: 14 }}>
      <div style={{ fontSize: 15, fontWeight: 400 }}>Parse report — nothing imported yet</div>
      <dl style={{ margin: "12px 0 0", display: "grid", gap: 6 }}>
        <Stat label="Ledger masters" value={`${report.counts.ledger_masters}`} />
        <Stat label="Vouchers" value={`${report.counts.vouchers}`} />
        <Stat
          label="Ledgers matched to existing accounts"
          value={`${report.matched.length} of ${report.matched.length + report.unmatched.length}`}
        />
      </dl>

      {report.errors.length > 0 && (
        <Warn>
          {report.errors.length} row(s) cannot be imported exactly — Tally amounts must convert
          to whole paise and dates must be readable; nothing is rounded silently. Fix these in
          Tally and re-export:
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {report.errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </Warn>
      )}

      {report.unbalanced.length > 0 && (
        <Warn>
          Unbalanced voucher(s) — debits and credits must be equal to enter the books:
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {report.unbalanced.map((v) => (
              <li key={v.voucher_id}>
                Tally voucher <span className="ident">{v.voucher_id}</span> is off by{" "}
                {inrPrecise(Math.abs(v.diff_paise))}
              </li>
            ))}
          </ul>
        </Warn>
      )}

      {/* THE reconciliation report: our arithmetic vs Tally's own stated closing balances. */}
      <details open={mismatches.length > 0} style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--color-ink-muted)" }}>
          Checksum reconciliation — {mismatches.length === 0
            ? "every stated closing balance ties out"
            : `${mismatches.length} ledger(s) do NOT tie out`}
          {unknown.length > 0 ? ` (${unknown.length} stated no closing balance)` : ""}
        </summary>
        <div style={{ overflowX: "auto" }}>
          <table className="tnum" style={{ borderCollapse: "collapse", fontSize: 12, marginTop: 8, width: "100%" }}>
            <thead>
              <tr style={{ color: "var(--color-ink-muted)", textAlign: "left" }}>
                <th style={TH}>Ledger</th>
                <th style={{ ...TH, textAlign: "right" }}>Debits</th>
                <th style={{ ...TH, textAlign: "right" }}>Credits</th>
                <th style={{ ...TH, textAlign: "right" }}>Computed closing</th>
                <th style={{ ...TH, textAlign: "right" }}>Tally says</th>
                <th style={TH}>Ties out?</th>
              </tr>
            </thead>
            <tbody>
              {report.reconciliation.map((r) => (
                <tr key={r.name}>
                  <td style={{ ...TD, fontVariantNumeric: "normal" }}>{r.name}</td>
                  <td style={{ ...TD, textAlign: "right" }}>{inrPrecise(r.debits_paise)}</td>
                  <td style={{ ...TD, textAlign: "right" }}>{inrPrecise(r.credits_paise)}</td>
                  <td style={{ ...TD, textAlign: "right" }}>{drCr(r.computed_closing_paise)}</td>
                  <td style={{ ...TD, textAlign: "right" }}>
                    {r.stated_closing_paise === null ? "not stated" : drCr(r.stated_closing_paise)}
                  </td>
                  <td style={{ ...TD, color: r.match === false ? "var(--color-verify-unbacked)" : undefined }}>
                    {r.match === null ? "unknown" : r.match ? "yes" : "NO"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {mismatches.length > 0 && (
          <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginTop: 6 }}>
            A mismatch means the vouchers in this file do not add up to the closing balance Tally
            itself stated — usually a partial export. You can still import; the mismatch stays
            recorded above, never absorbed.
          </div>
        )}
      </details>

      {report.unmatched.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 13, marginBottom: 6 }}>
            Map {report.unmatched.length} Tally ledger(s) with no matching account
          </div>
          {report.unmatched.map((u) => (
            <MappingRow
              key={u.name}
              unmatched={u}
              accounts={report.accounts}
              entry={mapping[u.name]}
              onChange={(entry) => setMapping({ ...mapping, [u.name]: entry })}
            />
          ))}
        </div>
      )}

      {!blocked && (
        <div style={{ marginTop: 14 }}>
          <label style={{ display: "block", fontSize: 12, color: "var(--color-ink-muted)" }}>
            Type <span className="ident">{report.confirm_word}</span> to arm the import
            <input
              className="ident"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              aria-label="Confirm word"
              style={{ ...INPUT, marginTop: 4, maxWidth: 200 }}
            />
          </label>
        </div>
      )}
      {blocked && (
        <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginTop: 12 }}>
          The problems listed above must be fixed in Tally first — this import refuses to guess.
        </div>
      )}
    </div>
  );
}

function MappingRow({
  unmatched,
  accounts,
  entry,
  onChange,
}: {
  unmatched: { name: string; parent: string | null; suggested_type: string | null };
  accounts: ParseReport["accounts"];
  entry: MappingEntry | undefined;
  onChange: (entry: MappingEntry | undefined) => void;
}) {
  const creating = entry !== undefined && "create" in entry;
  const create = creating ? entry.create : null;

  return (
    <div
      style={{
        border: "1px solid var(--color-border)",
        borderRadius: 4,
        padding: "10px 12px",
        marginBottom: 8,
        fontSize: 13,
      }}
    >
      <div>
        <span style={{ fontWeight: 500 }}>{unmatched.name}</span>
        {unmatched.parent && (
          <span style={{ color: "var(--color-ink-muted)" }}> · Tally group: {unmatched.parent}</span>
        )}
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 8, alignItems: "center" }}>
        <select
          aria-label={`Map ${unmatched.name}`}
          value={creating ? "__create__" : entry ? `${entry.account_id}` : ""}
          onChange={(e) => {
            const v = e.target.value;
            if (v === "") onChange(undefined);
            else if (v === "__create__")
              onChange({
                create: {
                  code: "",
                  name: unmatched.name,
                  // the parser's suggestion prefills; blank when unknown — the user decides
                  account_type: unmatched.suggested_type ?? "",
                },
              });
            else onChange({ account_id: Number(v) });
          }}
          style={INPUT}
        >
          <option value="">— choose —</option>
          <option value="__create__">Create a new account</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.code} · {a.name} ({a.account_type})
            </option>
          ))}
        </select>
        {create && (
          <>
            <input
              aria-label={`Code for ${unmatched.name}`}
              placeholder="Code"
              value={create.code}
              onChange={(e) => onChange({ create: { ...create, code: e.target.value } })}
              style={{ ...INPUT, width: 90 }}
            />
            <select
              aria-label={`Type for ${unmatched.name}`}
              value={create.account_type}
              onChange={(e) => onChange({ create: { ...create, account_type: e.target.value } })}
              style={INPUT}
            >
              <option value="">type…</option>
              {ACCOUNT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            {unmatched.suggested_type && (
              <span style={{ color: "var(--color-ink-faint)", fontSize: 11 }}>
                suggested from the Tally group: {unmatched.suggested_type}
              </span>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/** Debit-positive paise -> "₹x Dr" / "₹x Cr" / "₹0". */
export function drCr(paise: number): string {
  if (paise === 0) return inrPrecise(0);
  return `${inrPrecise(Math.abs(paise))} ${paise > 0 ? "Dr" : "Cr"}`;
}

export function TallyEmpty() {
  return (
    <Empty>
      Export your books from Tally (Display → Day Book → Export, XML format — masters and
      vouchers) and choose the file here. You will see a full parse and reconciliation report
      before anything is written.
    </Empty>
  );
}

const PANEL: React.CSSProperties = {
  border: "1px solid var(--color-border-strong)",
  borderRadius: 8,
  padding: "14px 16px",
  background: "var(--color-surface)",
  fontSize: 13,
};

const BUTTON: React.CSSProperties = {
  background: "var(--color-accent)",
  color: "var(--color-on-accent)",
  border: "none",
  padding: "8px 16px",
  borderRadius: 4,
  fontSize: 13,
  fontWeight: 400,
  fontFamily: "inherit",
};

const INPUT: React.CSSProperties = {
  padding: "6px 8px",
  borderRadius: 4,
  border: "1px solid var(--color-border-strong)",
  background: "var(--color-surface)",
  color: "var(--color-ink)",
  fontSize: 13,
  fontFamily: "inherit",
};

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

function Warn({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        marginTop: 12,
        border: "1px solid var(--color-warn)",
        borderRadius: 4,
        padding: "10px 12px",
        fontSize: 13,
      }}
    >
      {children}
    </div>
  );
}
