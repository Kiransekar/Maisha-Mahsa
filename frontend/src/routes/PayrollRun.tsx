// P0-4 PAYROLL RUN FLOW — /payroll-run: employees + last run, then preview → typed confirm →
// the run lands in the EXISTING approvals queue (rule PAYROLL-005) → artifacts download.
//
// Trust rules carried in (docs/WS7_BUILD_CONTRACT.md):
//   · Badge state comes from the SERVER payload only; an unknown state falls to ✕, never ✓
//     (badgeState, reused from Filings). This screen cannot fabricate a verified figure.
//   · A null amount renders "not yet known — we don't guess", never ₹0 (amountText, reused).
//   · INVARIANT 9 made visible: the Confirm button cannot enable before a preview exists
//     (runConfirmDisabledReason) and the typed phrase is the month being run.
//   · The receipt says plainly that the run is a DRAFT awaiting approval — confirming here is
//     not a disbursement, and the copy comes from the server (approval.note), not this file.
//   · T4: preview figures older than PAYLOAD_MAX_AGE_MS downgrade via effectiveState.

import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiBlob, ApiError } from "../lib/api";
import {
  effectiveState,
  isRestricted,
  LockChip,
  VerifiedNumber,
  type RestrictedField,
  type VerifyState,
  type Working,
} from "../components/VerifiedNumber";
import { ErrorState } from "../components/ErrorState";
import { useTraceId } from "../lib/trace";
import { ago, confirmOk, PAYLOAD_MAX_AGE_MS, useNow } from "./Approvals";
import { amountText, badgeState, confirmDisabledReason, type ServerFigure } from "./Filings";
import { Empty, H2, Header } from "./Today";

// ── types (server shapes from app/web/api_payroll.py) ────────────────────────

export type OverviewEmployee = {
  employee_id: number;
  employee_code: string;
  name: string;
  state_code: string | null;
  date_of_joining: string;
  // T11: masked server-side to a RestrictedField for roles without salary_detail clearance.
  monthly_net_paise: number | null | RestrictedField;
  has_salary_structure: boolean;
};

export type ArtifactLinks = {
  ecr: string;
  per_employee: { employee_id: number; name: string; payslip: string; form16: string }[];
};

type LastRun = {
  payroll_run_id: number;
  month_year: string;
  run_date: string;
  status: string;
  figures: ServerFigure[];
  artifacts: ArtifactLinks;
};

type Overview = {
  as_of: string;
  employees: OverviewEmployee[];
  last_run: LastRun | null;
  runs_pending_approval: number;
  can_run: boolean;
  run_denied_reason: string | null;
};

export type RunEmployee = {
  employee_id: number;
  employee_code: string;
  name: string;
  // T11: each per-employee figure may arrive masked (the value never left the server).
  figures: (ServerFigure | RestrictedField)[];
};

export type RunPreview = {
  kind: string;
  month_year: string;
  as_of: string;
  mahsa_up: boolean;
  employee_count: number;
  employees: RunEmployee[];
  totals: ServerFigure[];
  verdict_hash: string | null;
  rule_pack_version: string | null;
  confirm_phrase: string;
  confirm_token: string;
  can_confirm: boolean;
  confirm_denied_reason: string | null;
  will_write: string[];
  approval_note: string;
  trace_id: string;
};

type RunReceipt = {
  committed: boolean;
  payroll_run_id: number;
  month_year: string;
  status: string;
  employee_count: number;
  verdict_hash: string | null;
  mahsa_up: boolean;
  audit_hash: string;
  timestamp: string;
  user_id: string;
  trace_id: string;
  approval: { queued: boolean; note: string; where: string };
  artifacts: ArtifactLinks;
};

// ── pure logic (tested in PayrollRun.test.ts) ────────────────────────────────

/** Render props for one badged server figure. The state goes through badgeState (whitelist —
 *  a hostile/typo'd server state falls to ✕, never ✓) and the T4 staleness downgrade; the
 *  amount goes through amountText (null is "not yet known", never ₹0). */
export function figureProps(
  f: ServerFigure,
  stale: boolean,
): { label: string; value: string; state: VerifyState; note: string | null; working: Working } {
  return {
    label: f.label,
    value: amountText(f.value_paise),
    state: effectiveState(badgeState(f.state), stale),
    note: f.working?.note ?? null,
    working: f.working,
  };
}

/** Why Confirm is disabled, in words — INVARIANT 9 first (no preview, no confirm), then the
 *  capability + typed-phrase gates shared with the filing flow. Null means enabled. */
export function runConfirmDisabledReason(
  hasPreview: boolean,
  canConfirm: boolean,
  serverReason: string | null,
  typedOk: boolean,
): string | null {
  if (!hasPreview) return "Preview the run first — nothing can be confirmed sight-unseen.";
  return confirmDisabledReason(canConfirm, serverReason, typedOk);
}

/** "YYYY-MM" for the month `now` sits in — the default a payroll run is prepared for. */
export function defaultMonth(now: Date): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** One figure slot: a T11-masked figure renders as an explicit lock chip (label + reason —
 *  never blank, never absent), everything else as the badged VerifiedNumber. */
export function FigureCard({
  f,
  stale,
}: {
  f: ServerFigure | RestrictedField;
  stale: boolean;
}) {
  if (isRestricted(f)) {
    return (
      <div
        style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: 8,
          padding: "14px 16px",
          minWidth: 220,
          flex: "1 1 220px",
        }}
      >
        <div style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>
          {f.label ?? "Restricted figure"}
        </div>
        <div style={{ marginTop: 8 }}>
          <LockChip reason={f.reason} />
        </div>
      </div>
    );
  }
  const p = figureProps(f, stale);
  return (
    <VerifiedNumber
      label={p.label}
      value={p.value}
      state={p.state}
      note={p.note}
      working={p.working}
    />
  );
}

// ── screen ───────────────────────────────────────────────────────────────────

export function PayrollRun() {
  const traceId = useTraceId("payroll-run");
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["payroll-run-overview"],
    queryFn: () => api<Overview>("/payroll/runs/overview"),
    refetchOnWindowFocus: true,
  });

  if (isLoading && !data) return <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>;
  if (error) {
    return (
      <div>
        <Header title="Payroll run" />
        <ErrorState error={error} traceId={traceId} onRetry={refetch} />
      </div>
    );
  }
  if (!data) return null;

  return (
    <section>
      <Header title="Payroll run" as_of={data.as_of} />
      <p style={{ color: "var(--color-ink-muted)", fontSize: 13, margin: "0 0 14px" }}>
        Preview computes every employee's month and has Mahsa recompute what it can — nothing is
        written. Confirming drafts the run; it is <strong style={{ fontWeight: 600 }}>released
        only through Approvals</strong>, never from this screen.
      </p>

      {data.runs_pending_approval > 0 && (
        <p
          style={{
            fontSize: 13,
            lineHeight: 1.55,
            margin: "0 0 14px",
            padding: "10px 12px",
            borderRadius: 4,
            border: "1px solid var(--color-verify-pending)",
            background: "var(--color-surface-sunk)",
          }}
        >
          <span className="tnum">{data.runs_pending_approval}</span> drafted run
          {data.runs_pending_approval === 1 ? "" : "s"} await
          {data.runs_pending_approval === 1 ? "s" : ""} sign-off —{" "}
          <Link to="/approvals" style={{ color: "var(--color-accent)" }}>
            decide in Approvals
          </Link>
          . No wages are released until then.
        </p>
      )}

      <RunFlow
        canRun={data.can_run}
        runDeniedReason={data.run_denied_reason}
        onCommitted={() => qc.invalidateQueries({ queryKey: ["payroll-run-overview"] })}
      />

      <H2>Last run</H2>
      {data.last_run === null ? (
        <Empty>No payroll run yet — preview one above.</Empty>
      ) : (
        <LastRunCard run={data.last_run} />
      )}

      <H2>Employees · {data.employees.length}</H2>
      {data.employees.length === 0 ? (
        <Empty>
          No active employees. Add them in the Payroll domain before running payroll.
        </Empty>
      ) : (
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
          <thead>
            <tr style={{ color: "var(--color-ink-muted)", textAlign: "left" }}>
              <th style={th()}>Code</th>
              <th style={th()}>Name</th>
              <th style={th()}>State</th>
              <th style={th()}>Joined</th>
              <th style={{ ...th(), textAlign: "right" }}>Monthly net (structure)</th>
            </tr>
          </thead>
          <tbody>
            {data.employees.map((e) => (
              <tr key={e.employee_id} style={{ borderTop: "1px solid var(--color-border)" }}>
                <td style={td()}>
                  <span className="ident">{e.employee_code}</span>
                </td>
                <td style={td()}>{e.name}</td>
                <td style={td()}>{e.state_code ?? "—"}</td>
                <td style={td()}>
                  <span className="tnum">{e.date_of_joining}</span>
                </td>
                <td style={{ ...td(), textAlign: "right" }}>
                  {/* T11: a masked salary is a visible lock, never a blank cell.
                      Invariant 2: no structure means UNKNOWN — never ₹0. */}
                  {isRestricted(e.monthly_net_paise) ? (
                    <LockChip reason={e.monthly_net_paise.reason} />
                  ) : (
                    <span className="tnum">{amountText(e.monthly_net_paise)}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function LastRunCard({ run }: { run: LastRun }) {
  const released = run.status === "approved";
  return (
    <div style={card()}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <strong style={{ fontSize: 15, fontWeight: 600 }}>
            {run.month_year} · <span className="ident">{run.status}</span>
          </strong>
          <div className="tnum" style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>
            run on {run.run_date}
          </div>
        </div>
        {run.status === "draft" && (
          <Link to="/approvals" style={{ color: "var(--color-accent)", fontSize: 13 }}>
            awaiting approval →
          </Link>
        )}
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 10 }}>
        {run.figures.map((f) => (
          <FigureCard key={f.target} f={f} stale={false} />
        ))}
      </div>
      {/* Statutory artifacts only once the run exists; drafts still print (a payslip is not a
          disbursement), and the status line above says plainly whether it was released. */}
      <ArtifactRow artifacts={run.artifacts} monthYear={run.month_year} released={released} />
    </div>
  );
}

// ── the run flow: month → preview → typed confirm → receipt ──────────────────

function RunFlow({
  canRun,
  runDeniedReason,
  onCommitted,
}: {
  canRun: boolean;
  runDeniedReason: string | null;
  onCommitted: () => void;
}) {
  const traceId = useTraceId("payroll-run-flow");
  const [month, setMonth] = useState(() => defaultMonth(new Date()));
  const [preview, setPreview] = useState<{ p: RunPreview; at: number } | null>(null);
  const [receipt, setReceipt] = useState<RunReceipt | null>(null);

  const run = useMutation({
    mutationFn: () =>
      api<RunPreview>("/payroll/runs/preview", {
        method: "POST",
        body: JSON.stringify({ month_year: month, trace_id: traceId }),
      }),
    onSuccess: (p) => {
      setReceipt(null);
      setPreview({ p, at: Date.now() });
    },
  });

  if (receipt) {
    return (
      <ReceiptCard
        receipt={receipt}
        onBack={() => {
          setReceipt(null);
          setPreview(null);
        }}
      />
    );
  }

  return (
    <div style={card()}>
      <H2>Run payroll</H2>
      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap" }}>
        <label style={{ fontSize: 12, color: "var(--color-ink-muted)" }}>
          Month
          <div style={{ marginTop: 4 }}>
            {/* native month input over a picker lib (ladder rung 4) */}
            <input
              type="month"
              value={month}
              onChange={(e) => {
                setMonth(e.target.value);
                setPreview(null); // a changed month invalidates what was previewed
              }}
              style={input()}
            />
          </div>
        </label>
        <button
          type="button"
          disabled={!month || run.isPending}
          onClick={() => run.mutate()}
          style={btn(Boolean(month) && !run.isPending, "var(--color-accent)")}
        >
          {run.isPending ? "Computing…" : "Preview the run"}
        </button>
      </div>
      {run.error != null && (
        <div style={{ marginTop: 12 }}>
          <ErrorState error={run.error} traceId={traceId} onRetry={() => run.mutate()} />
        </div>
      )}
      {preview && (
        <PreviewBlock
          preview={preview.p}
          previewedAt={preview.at}
          canRun={canRun}
          runDeniedReason={runDeniedReason}
          onRePreview={() => run.mutate()}
          onCommitted={(r) => {
            setReceipt(r);
            setPreview(null);
            onCommitted();
          }}
        />
      )}
    </div>
  );
}

function PreviewBlock({
  preview,
  previewedAt,
  canRun,
  runDeniedReason,
  onRePreview,
  onCommitted,
}: {
  preview: RunPreview;
  previewedAt: number;
  canRun: boolean;
  runDeniedReason: string | null;
  onRePreview: () => void;
  onCommitted: (r: RunReceipt) => void;
}) {
  const [typed, setTyped] = useState("");
  const now = useNow();
  const age = now - previewedAt;
  const stale = age > PAYLOAD_MAX_AGE_MS;
  const typedOk = confirmOk(typed, preview.confirm_phrase);
  const reason = runConfirmDisabledReason(
    true,
    preview.can_confirm && canRun,
    preview.confirm_denied_reason ?? runDeniedReason,
    typedOk,
  );

  const confirm = useMutation({
    mutationFn: () =>
      api<RunReceipt>("/payroll/runs/confirm", {
        method: "POST",
        body: JSON.stringify({
          month_year: preview.month_year,
          confirm_token: preview.confirm_token,
          confirm_text: typed,
          trace_id: preview.trace_id,
        }),
      }),
    onSuccess: onCommitted,
  });

  return (
    <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--color-border)" }}>
      {!preview.mahsa_up && (
        <p
          style={{
            fontSize: 13,
            margin: "0 0 12px",
            padding: "10px 12px",
            borderRadius: 4,
            border: "1px solid var(--color-verify-pending)",
            background: "var(--color-surface-sunk)",
          }}
        >
          Mahsa is unreachable: nothing below was independently recomputed, which is why no
          figure shows ✓. You may still draft the run — it will be recorded as unverified and
          still needs approval.
        </p>
      )}

      <p style={{ color: "var(--color-ink-faint)", fontSize: 12, margin: "0 0 10px" }}>
        Figures computed <span className="tnum">{ago(age)}</span>
        {stale ? " · re-preview before confirming for a ✓ you can rely on" : ""} ·{" "}
        <span className="tnum">{preview.employee_count}</span> employee
        {preview.employee_count === 1 ? "" : "s"}
      </p>

      {preview.employees.length === 0 && (
        <Empty>
          No employee has a salary structure effective for {preview.month_year} — there is
          nothing to run.
        </Empty>
      )}

      {preview.employees.map((e) => (
        <div key={e.employee_id} style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
            {e.name} <span className="ident" style={{ fontWeight: 400 }}>{e.employee_code}</span>
          </div>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {e.figures.map((f, i) => (
              <FigureCard key={f.target ?? `${e.employee_id}-${i}`} f={f} stale={stale} />
            ))}
          </div>
        </div>
      ))}

      {preview.totals.length > 0 && (
        <>
          <H2>Totals</H2>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {preview.totals.map((f) => (
              <FigureCard key={f.target} f={f} stale={stale} />
            ))}
          </div>
        </>
      )}

      {preview.verdict_hash && (
        <div style={{ fontSize: 11, color: "var(--color-ink-faint)", marginTop: 10 }}>
          sealed <span className="ident">{preview.verdict_hash}</span>
          {preview.rule_pack_version && <> · rules {preview.rule_pack_version}</>}
        </div>
      )}

      <H2>What confirming writes</H2>
      <ul style={{ fontSize: 13, color: "var(--color-ink-muted)", lineHeight: 1.6, marginTop: 0 }}>
        {preview.will_write.map((w) => (
          <li key={w}>{w}</li>
        ))}
      </ul>
      <p style={{ fontSize: 12, color: "var(--color-ink-faint)" }}>{preview.approval_note}</p>

      <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--color-border)" }}>
        <label
          htmlFor="payroll-run-confirm"
          style={{ fontSize: 13, lineHeight: 1.55, color: "var(--color-ink-muted)", display: "block" }}
        >
          The confirmation is bound to this exact preview — if the books moved and the figures
          changed, the server refuses it and nothing is written. To confirm you have read the
          figures, type <strong className="ident">{preview.confirm_phrase}</strong>.
        </label>
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <input
            id="payroll-run-confirm"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={preview.confirm_phrase}
            autoComplete="off"
            disabled={!(preview.can_confirm && canRun)}
            style={{ ...input(), fontFamily: "var(--font-mono)", minWidth: 180 }}
          />
          <button
            type="button"
            disabled={reason !== null || confirm.isPending || preview.employees.length === 0}
            onClick={() => confirm.mutate()}
            style={btn(
              reason === null && !confirm.isPending && preview.employees.length > 0,
              "var(--color-accent)",
            )}
          >
            {confirm.isPending ? "Drafting…" : "Confirm — draft the run"}
          </button>
          <button type="button" onClick={onRePreview} style={btn(true, "transparent")}>
            Re-preview
          </button>
        </div>
        {reason && (
          <div style={{ color: "var(--color-ink-faint)", fontSize: 12, marginTop: 6 }}>{reason}</div>
        )}
        {confirm.error != null && (
          <ConfirmFailure error={confirm.error} phrase={preview.confirm_phrase} />
        )}
      </div>
    </div>
  );
}

/** 4-question template for a failed CONFIRM, with the precision a refusing server allows
 *  (mirrors Filings.RecordFailure: a 4xx answer means nothing was written). */
function ConfirmFailure({ error, phrase }: { error: unknown; phrase: string }) {
  const status = error instanceof ApiError ? error.status : null;
  const what =
    status === 409
      ? "The confirmation belonged to a different preview — the figures were recomputed from the current books and did not match, so the server refused to draft the run."
      : status === 400
        ? "The typed confirmation did not match, so nothing was written."
        : status === 403
          ? "Your role cannot run payroll (a books-writing role is required)."
          : status !== null
            ? `The server refused this run (${status}).`
            : "The request failed before we got an answer back.";
  const safe =
    status !== null
      ? "Yes. The server answered and refused — no run was drafted, no wages were released."
      : "We can't confirm either way, so we won't claim it. No wages are ever released from this screen — release needs an Approvals decision. Check the audit trail for a payroll.run_recorded entry before retrying.";
  return (
    <div
      style={{
        border: "1px solid var(--color-verify-unbacked)",
        borderRadius: 4,
        padding: "10px 12px",
        marginTop: 10,
        fontSize: 12,
        lineHeight: 1.55,
      }}
    >
      <div>
        <strong style={{ fontWeight: 600 }}>What happened.</strong> {what}
      </div>
      <div>
        <strong style={{ fontWeight: 600 }}>Is your money safe.</strong> {safe}
      </div>
      <div>
        <strong style={{ fontWeight: 600 }}>What to do next.</strong>{" "}
        {status === 409
          ? "Re-preview, read the fresh figures, and confirm those."
          : status === 400
            ? `Type ${phrase} exactly, then confirm again.`
            : "Open the Audit Room and check for a payroll.run_recorded entry before retrying. If it isn't there, retry is safe."}
      </div>
      <div className="ident" style={{ color: "var(--color-ink-faint)", marginTop: 4 }}>
        ref payroll-run-{phrase}-{status ?? "no-response"}
      </div>
    </div>
  );
}

/** A persistent receipt (never a toast): the draft is real, and so is the approval it needs. */
function ReceiptCard({ receipt, onBack }: { receipt: RunReceipt; onBack: () => void }) {
  return (
    <div
      style={{
        border: "1px solid var(--color-verify-pending)",
        background: "var(--color-surface)",
        borderRadius: 8,
        padding: "16px 18px",
        fontSize: 13,
        lineHeight: 1.6,
        marginBottom: 12,
      }}
    >
      <strong style={{ fontWeight: 600 }}>
        Run {receipt.month_year} drafted · <span className="ident">{receipt.status}</span>
      </strong>
      {/* The honest sentence, from the server, verbatim — a draft is not a disbursement. */}
      <p style={{ margin: "8px 0", color: "var(--color-ink-muted)" }}>{receipt.approval.note}</p>
      <p style={{ margin: "8px 0" }}>
        <Link to={receipt.approval.where} style={{ color: "var(--color-accent)" }}>
          Decide it in Approvals →
        </Link>
      </p>
      <div style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>
        audit hash <span className="ident">{receipt.audit_hash}</span>
      </div>
      {receipt.verdict_hash && (
        <div style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>
          verdict <span className="ident">{receipt.verdict_hash}</span>
        </div>
      )}
      <div style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>
        trace <span className="ident">{receipt.trace_id}</span>
      </div>
      <div className="tnum" style={{ color: "var(--color-ink-faint)", fontSize: 12 }}>
        {receipt.timestamp} · by {receipt.user_id}
      </div>
      <ArtifactRow
        artifacts={receipt.artifacts}
        monthYear={receipt.month_year}
        released={false}
      />
      <div style={{ marginTop: 12 }}>
        <button type="button" onClick={onBack} style={btn(true, "transparent")}>
          Back
        </button>
      </div>
    </div>
  );
}

// ── artifacts ────────────────────────────────────────────────────────────────

function ArtifactRow({
  artifacts,
  monthYear,
  released,
}: {
  artifacts: ArtifactLinks;
  monthYear: string;
  released: boolean;
}) {
  const [err, setErr] = useState<string | null>(null);
  const download = async (path: string, filename: string) => {
    setErr(null);
    try {
      // The /api paths from the server include the /api prefix apiBlob adds — strip it once.
      const blob = await apiBlob(path.replace(/^\/api/, ""));
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(
        e instanceof ApiError && e.status === 403
          ? "Your role cannot export documents (export capability required)."
          : "The download failed — the run record stands; retry from this screen.",
      );
    }
  };
  return (
    <div style={{ marginTop: 12 }}>
      <div
        style={{
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          fontSize: 10,
          color: "var(--color-ink-faint)",
          marginBottom: 6,
        }}
      >
        Statutory documents{released ? "" : " · run not yet released"}
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {artifacts.per_employee.map((e) => (
          <span key={e.employee_id} style={{ display: "inline-flex", gap: 6 }}>
            <button
              type="button"
              onClick={() => download(e.payslip, `payslip-${e.employee_id}-${monthYear}.pdf`)}
              style={btn(true, "transparent")}
            >
              Payslip · {e.name}
            </button>
            <button
              type="button"
              onClick={() => download(e.form16, `form16-${e.employee_id}.pdf`)}
              style={btn(true, "transparent")}
            >
              Form 16 · {e.name}
            </button>
          </span>
        ))}
        <button
          type="button"
          onClick={() => download(artifacts.ecr, `ecr-${monthYear}.txt`)}
          style={btn(true, "transparent")}
        >
          EPFO ECR file
        </button>
      </div>
      {err && (
        <div style={{ color: "var(--color-verify-unbacked)", fontSize: 12, marginTop: 6 }}>
          {err}
        </div>
      )}
    </div>
  );
}

// ── shared bits (same closed style set as Filings) ───────────────────────────

function th(): React.CSSProperties {
  return { padding: "6px 8px", fontWeight: 400, fontSize: 12 };
}

function td(): React.CSSProperties {
  return { padding: "8px" };
}

function card(): React.CSSProperties {
  return {
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: 8,
    padding: "16px 18px",
    marginTop: 12,
    marginBottom: 12,
  };
}

function input(): React.CSSProperties {
  return {
    border: "1px solid var(--color-border-strong)",
    background: "var(--color-ground)",
    color: "var(--color-ink)",
    borderRadius: 4,
    padding: "7px 10px",
    fontSize: 13,
    fontFamily: "inherit",
  };
}

function btn(enabled: boolean, background: string): React.CSSProperties {
  return {
    background: enabled ? background : "var(--color-surface-sunk)",
    color:
      enabled && background !== "transparent" ? "var(--color-on-accent)" : "var(--color-ink-muted)",
    border: background === "transparent" ? "1px solid var(--color-border-strong)" : "none",
    padding: "7px 14px",
    borderRadius: 4,
    fontSize: 13,
    fontFamily: "inherit",
    cursor: enabled ? "pointer" : "not-allowed",
  };
}
