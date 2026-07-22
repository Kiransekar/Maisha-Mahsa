// P0-1 FILING FLOW — /file: the missing end of the core loop.
//
// The queue lists every not-yet-filed obligation; each row opens a review → typed-confirm →
// receipt flow over the server's preview/confirm endpoints (app/web/api_filings.py).
//
// Trust rules carried in (docs/WS7_BUILD_CONTRACT.md):
//   · Badge state comes from the SERVER payload only; an unknown state falls to ✕, never ✓
//     (badgeState below). This screen cannot fabricate a verified figure.
//   · A null amount renders "not yet known — we don't guess", never ₹0 (amountText).
//   · Typed confirm reuses the Approvals gate EXACTLY (confirmOk) — no accidental path.
//   · An Accountant sees the queue and the preview; the confirm is DISABLED with the
//     capability-derived reason the server's own hard gate would give — not hidden (T11-adjacent,
//     and the WS5.2 Owner/Admin gate stays server-side; this button is honesty, not enforcement).
//   · T5: the receipt says "recorded as filed — keep your portal acknowledgement" and offers the
//     attempt-evidence bundle for penalty-waiver requests. It never claims portal submission.
//   · T4: preview figures older than PAYLOAD_MAX_AGE_MS downgrade via effectiveState.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../lib/api";
import { inr } from "../lib/money";
import {
  effectiveState,
  VerifiedNumber,
  VerifyChip,
  type VerifyState,
  type Working,
} from "../components/VerifiedNumber";
import { ErrorState } from "../components/ErrorState";
import { useTraceId } from "../lib/trace";
import { ago, confirmOk, PAYLOAD_MAX_AGE_MS, useNow } from "./Approvals";
import { Empty, H2, Header } from "./Today";

// ── types (server shapes from app/web/api_filings.py) ────────────────────────

export type QueueItem = {
  id: number;
  domain: string;
  form_name: string;
  filing_period: string | null;
  due_date: string;
  status: string;
  days_overdue: number;
  due_in_days: number;
  kind: "gstr3b" | "tds" | "deadline";
};

type Queue = {
  as_of: string;
  can_confirm: boolean;
  confirm_denied_reason: string | null;
  items: QueueItem[];
};

export type ServerFigure = {
  target: string;
  label: string;
  value_paise: number | null;
  state: string;
  working: Working;
};

type Preview = {
  kind: string;
  as_of: string;
  mahsa_up: boolean;
  figures: ServerFigure[];
  verdict_hash: string | null;
  rule_pack_version: string | null;
  confirm_phrase: string;
  confirm_token: string;
  can_confirm: boolean;
  confirm_denied_reason: string | null;
  will_record: string[];
  recorded_meaning: string;
  trace_id: string;
};

type FilingReceipt = {
  recorded: boolean;
  recorded_as: string;
  portal_submission: boolean;
  label: string;
  kind: string;
  audit_hash: string;
  timestamp: string;
  user_id: string;
  verdict_hash: string | null;
  mahsa_up: boolean;
  trace_id: string;
};

// ── pure logic (tested in Filings.test.ts) ───────────────────────────────────

/** Server state -> chip state. Whitelist: anything unrecognised is ✕ (unbacked), NEVER ✓.
 *  Mutation this guards against: `return s as VerifyState` would let a typo'd or hostile
 *  server state render as whatever it claims — including "verified". */
export function badgeState(s: string): VerifyState {
  return s === "verified" || s === "honest_pending" || s === "unbacked" ? s : "unbacked";
}

/** Invariant 2: a null amount is UNKNOWN — never ₹0, never blank. */
export function amountText(paise: number | null): string {
  return paise === null ? "not yet known — we don't guess" : inr(paise);
}

/** Whole rupees typed in a form -> integer paise. Integer-only (statutory return figures are
 *  rupee amounts); anything else is null so the caller disables preview instead of guessing. */
export function rupeesToPaise(text: string): number | null {
  const t = text.trim();
  if (!/^\d+$/.test(t)) return null;
  return Number(t) * 100;
}

/** Why the Record button is disabled, in words — capability first (the server's own reason for
 *  this caller), then the typed gate. Null means enabled. */
export function confirmDisabledReason(
  canConfirm: boolean,
  serverReason: string | null,
  typedOk: boolean,
): string | null {
  if (!canConfirm) {
    return (
      (serverReason ?? "Your role cannot record a statutory filing.") +
      " You can review the figures; recording is reserved to Owner/Admin."
    );
  }
  if (!typedOk) return "Nothing is recorded until the typed confirmation matches.";
  return null;
}

// ── screen ───────────────────────────────────────────────────────────────────

export function Filings() {
  const traceId = useTraceId("filings");
  const [active, setActive] = useState<QueueItem | null>(null);
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["filings"],
    queryFn: () => api<Queue>("/filings"),
    refetchOnWindowFocus: true,
  });

  if (isLoading && !data) return <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>;
  if (error) {
    return (
      <div>
        <Header title="File returns" />
        <ErrorState error={error} traceId={traceId} onRetry={refetch} />
      </div>
    );
  }
  if (!data) return null;

  const overdue = data.items.filter((i) => i.days_overdue > 0);
  const due = data.items.filter((i) => i.days_overdue === 0);

  return (
    <section>
      <Header title="File returns" as_of={data.as_of} />
      <p style={{ color: "var(--color-ink-muted)", fontSize: 13, margin: "0 0 14px" }}>
        This screen <strong style={{ fontWeight: 600 }}>records</strong> filings in your books and
        seals the figures you saw as attempt evidence. It does not submit anything to a government
        portal — the portal acknowledgement remains your statutory proof.
      </p>

      {!data.can_confirm && (
        <p
          style={{
            fontSize: 13,
            lineHeight: 1.55,
            margin: "0 0 14px",
            padding: "10px 12px",
            borderRadius: 4,
            border: "1px solid var(--color-verify-pending)",
            background: "var(--color-surface-sunk)",
            color: "var(--color-ink-muted)",
          }}
        >
          {data.confirm_denied_reason ?? "Your role cannot record a statutory filing."} You can
          review every return and its figures; the Record step is reserved to Owner/Admin.
        </p>
      )}

      {active ? (
        <FilingFlow
          item={active}
          onBack={() => setActive(null)}
          onRecorded={() => qc.invalidateQueries({ queryKey: ["filings"] })}
        />
      ) : (
        <>
          <H2>Overdue · {overdue.length}</H2>
          {overdue.length === 0 ? (
            <Empty>Nothing is overdue.</Empty>
          ) : (
            overdue.map((i) => <QueueRow key={i.id} item={i} onOpen={() => setActive(i)} />)
          )}
          <H2>Due · {due.length}</H2>
          {due.length === 0 ? (
            <Empty>
              Nothing else is pending on the compliance calendar. Deadlines seeded in the
              Compliance domain appear here.
            </Empty>
          ) : (
            due.map((i) => <QueueRow key={i.id} item={i} onOpen={() => setActive(i)} />)
          )}
        </>
      )}
    </section>
  );
}

function QueueRow({ item, onOpen }: { item: QueueItem; onOpen: () => void }) {
  const late = item.days_overdue > 0;
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 16,
        flexWrap: "wrap",
        padding: "10px 12px",
        marginBottom: 6,
        borderRadius: 4,
        border: "1px solid var(--color-border)",
        borderLeft: `3px solid ${late ? "var(--color-verify-unbacked)" : "var(--color-border-strong)"}`,
        background: "var(--color-surface)",
      }}
    >
      <div>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{item.form_name}</div>
        <div className="tnum" style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>
          due {item.due_date}
          {late
            ? ` · overdue by ${item.days_overdue} day${item.days_overdue === 1 ? "" : "s"} — late fee and interest accrue`
            : item.due_in_days === 0
              ? " · due today"
              : ` · in ${item.due_in_days} day${item.due_in_days === 1 ? "" : "s"}`}
        </div>
      </div>
      <button type="button" onClick={onOpen} style={btn(true, "transparent")}>
        Review &amp; record
      </button>
    </div>
  );
}

// ── the per-return flow: form → preview → typed confirm → receipt ────────────

function FilingFlow({
  item,
  onBack,
  onRecorded,
}: {
  item: QueueItem;
  onBack: () => void;
  onRecorded: () => void;
}) {
  const [preview, setPreview] = useState<{ p: Preview; body: unknown; at: number } | null>(null);
  const [receipt, setReceipt] = useState<FilingReceipt | null>(null);

  if (receipt) return <ReceiptCard receipt={receipt} onBack={onBack} />;

  return (
    <div>
      <button type="button" onClick={onBack} style={btn(true, "transparent")}>
        ← Back to the queue
      </button>
      <H2>
        {item.form_name} · due {item.due_date}
      </H2>
      {!preview && (
        <FilingForm item={item} onPreviewed={(p, body) => setPreview({ p, body, at: Date.now() })} />
      )}
      {preview && (
        <PreviewCard
          item={item}
          preview={preview.p}
          previewBody={preview.body}
          previewedAt={preview.at}
          onRePreview={() => setPreview(null)}
          onRecorded={(r) => {
            setReceipt(r);
            onRecorded();
          }}
        />
      )}
    </div>
  );
}

/** The input form per kind. Preview is a READ + evidence seal — no filing is written by it. */
function FilingForm({
  item,
  onPreviewed,
}: {
  item: QueueItem;
  onPreviewed: (p: Preview, body: unknown) => void;
}) {
  const traceId = useTraceId(`filing-${item.id}`);
  const today = new Date().toISOString().slice(0, 10);
  const [f, setF] = useState<Record<string, string>>({
    filing_period: item.filing_period ?? "",
    due_date: item.due_date,
    filed_date: today,
    return_type: item.kind === "tds" ? guessTdsType(item.form_name) : "",
    quarter: item.filing_period ?? "",
    acknowledgement: "",
    is_nil: "",
    out_igst: "0",
    out_cgst: "0",
    out_sgst: "0",
    itc_igst: "0",
    itc_cgst: "0",
    itc_sgst: "0",
    total_deducted: "0",
  });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF((prev) => ({ ...prev, [k]: e.target.value }));

  const { body, path, invalid } = buildPreviewRequest(item, f);
  const run = useMutation({
    mutationFn: () =>
      api<Preview>(`${path}?trace_id=${encodeURIComponent(traceId)}`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (p) => onPreviewed(p, body),
  });

  return (
    <div style={card()}>
      <p style={{ color: "var(--color-ink-muted)", fontSize: 13, marginTop: 0 }}>
        Enter the return exactly as you will file it on the portal. Previewing computes the
        figures, has Mahsa recompute what it can, and seals what you were shown as attempt
        evidence — it records no filing.
      </p>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {item.kind === "gstr3b" && (
          <>
            <Field label="Filing period (YYYY-MM)">
              <input value={f.filing_period} onChange={set("filing_period")} style={input()} />
            </Field>
            <Field label="Due date">
              <input type="date" value={f.due_date} onChange={set("due_date")} style={input()} />
            </Field>
            <Field label="Filed date (portal date)">
              <input type="date" value={f.filed_date} onChange={set("filed_date")} style={input()} />
            </Field>
            <Field label="Nil return">
              <select value={f.is_nil} onChange={set("is_nil")} style={input()}>
                <option value="">No</option>
                <option value="yes">Yes</option>
              </select>
            </Field>
            {(["igst", "cgst", "sgst"] as const).map((h) => (
              <Field key={`out_${h}`} label={`Output ${h.toUpperCase()} (₹, whole)`}>
                <input value={f[`out_${h}`]} onChange={set(`out_${h}`)} style={input()} inputMode="numeric" />
              </Field>
            ))}
            {(["igst", "cgst", "sgst"] as const).map((h) => (
              <Field key={`itc_${h}`} label={`ITC ${h.toUpperCase()} (₹, whole)`}>
                <input value={f[`itc_${h}`]} onChange={set(`itc_${h}`)} style={input()} inputMode="numeric" />
              </Field>
            ))}
          </>
        )}
        {item.kind === "tds" && (
          <>
            <Field label="Return type">
              <select value={f.return_type} onChange={set("return_type")} style={input()}>
                <option value="24Q">24Q</option>
                <option value="26Q">26Q</option>
                <option value="27Q">27Q</option>
              </select>
            </Field>
            <Field label="Quarter (e.g. 2026-Q1)">
              <input value={f.quarter} onChange={set("quarter")} style={input()} />
            </Field>
            <Field label="Due date">
              <input type="date" value={f.due_date} onChange={set("due_date")} style={input()} />
            </Field>
            <Field label="Filed date (portal date)">
              <input type="date" value={f.filed_date} onChange={set("filed_date")} style={input()} />
            </Field>
            <Field label="Total TDS deducted (₹, whole)">
              <input
                value={f.total_deducted}
                onChange={set("total_deducted")}
                style={input()}
                inputMode="numeric"
              />
            </Field>
          </>
        )}
        {item.kind === "deadline" && (
          <>
            <Field label="Filed date">
              <input type="date" value={f.filed_date} onChange={set("filed_date")} style={input()} />
            </Field>
            <Field label="Portal acknowledgement no. (optional)">
              <input value={f.acknowledgement} onChange={set("acknowledgement")} style={input()} />
            </Field>
          </>
        )}
      </div>
      <div style={{ marginTop: 14 }}>
        <button
          type="button"
          disabled={invalid !== null || run.isPending}
          onClick={() => run.mutate()}
          style={btn(invalid === null && !run.isPending, "var(--color-accent)")}
        >
          {run.isPending ? "Computing…" : "Preview the figures"}
        </button>
        {invalid && (
          <div style={{ color: "var(--color-ink-faint)", fontSize: 12, marginTop: 6 }}>{invalid}</div>
        )}
      </div>
      {run.error != null && (
        <div style={{ marginTop: 12 }}>
          <ErrorState error={run.error} traceId={traceId} onRetry={() => run.mutate()} />
        </div>
      )}
    </div>
  );
}

/** ponytail: form-name heuristic mirror of the server's `_kind_of`; the select stays editable so
 *  a wrong guess costs one click, never a wrong filing (the typed confirm names the real type). */
function guessTdsType(formName: string): string {
  const n = formName.toUpperCase();
  if (n.includes("26Q")) return "26Q";
  if (n.includes("27Q")) return "27Q";
  return "24Q";
}

export function buildPreviewRequest(
  item: QueueItem,
  f: Record<string, string>,
): { body: unknown; path: string; invalid: string | null } {
  if (item.kind === "gstr3b") {
    const heads = ["igst", "cgst", "sgst"] as const;
    const out: Record<string, number> = {};
    const itc: Record<string, number> = {};
    for (const h of heads) {
      const o = rupeesToPaise(f[`out_${h}`]);
      const c = rupeesToPaise(f[`itc_${h}`]);
      if (o === null || c === null) {
        return { body: null, path: "", invalid: "Amounts must be whole rupees (digits only)." };
      }
      out[h] = o;
      itc[h] = c;
    }
    return {
      path: "/filings/gstr3b/preview",
      invalid: null,
      body: {
        filing_period: f.filing_period,
        due_date: f.due_date,
        filed_date: f.filed_date || null,
        is_nil: f.is_nil === "yes",
        output: out,
        itc_available: itc,
      },
    };
  }
  if (item.kind === "tds") {
    const t = rupeesToPaise(f.total_deducted);
    if (t === null) {
      return { body: null, path: "", invalid: "Amounts must be whole rupees (digits only)." };
    }
    return {
      path: "/filings/tds/preview",
      invalid: null,
      body: {
        return_type: f.return_type || "24Q",
        quarter: f.quarter,
        due_date: f.due_date,
        filed_date: f.filed_date || null,
        total_deducted: t,
      },
    };
  }
  return {
    path: `/filings/deadline/${item.id}/preview`,
    invalid: null,
    body: { filed_date: f.filed_date, acknowledgement: f.acknowledgement || null },
  };
}

function PreviewCard({
  item,
  preview,
  previewBody,
  previewedAt,
  onRePreview,
  onRecorded,
}: {
  item: QueueItem;
  preview: Preview;
  previewBody: unknown;
  previewedAt: number;
  onRePreview: () => void;
  onRecorded: (r: FilingReceipt) => void;
}) {
  const [typed, setTyped] = useState("");
  const now = useNow();
  const age = now - previewedAt;
  const stale = age > PAYLOAD_MAX_AGE_MS;
  const typedOk = confirmOk(typed, preview.confirm_phrase);
  const reason = confirmDisabledReason(preview.can_confirm, preview.confirm_denied_reason, typedOk);

  const confirmPath =
    item.kind === "gstr3b"
      ? "/filings/gstr3b/confirm"
      : item.kind === "tds"
        ? "/filings/tds/confirm"
        : `/filings/deadline/${item.id}/confirm`;

  const record = useMutation({
    mutationFn: () =>
      api<FilingReceipt>(confirmPath, {
        method: "POST",
        body: JSON.stringify({
          inputs: previewBody,
          confirm_token: preview.confirm_token,
          confirm_text: typed,
          trace_id: preview.trace_id,
        }),
      }),
    onSuccess: onRecorded,
  });

  return (
    <div style={card()}>
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
          Mahsa is unreachable: nothing below was independently recomputed, which is why no figure
          shows ✓. You may still record the filing — it will be recorded as unverified.
        </p>
      )}

      <p style={{ color: "var(--color-ink-faint)", fontSize: 12, margin: "0 0 10px" }}>
        Figures computed <span className="tnum">{ago(age)}</span>
        {stale ? " · re-preview before recording for a ✓ you can rely on" : ""}
      </p>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {preview.figures.map((f) => (
          <VerifiedNumber
            key={f.target}
            label={f.label}
            value={amountText(f.value_paise)}
            state={effectiveState(badgeState(f.state), stale)}
            note={f.working.note}
            working={f.working}
          />
        ))}
      </div>

      {preview.verdict_hash && (
        <div style={{ fontSize: 11, color: "var(--color-ink-faint)", marginTop: 10 }}>
          sealed <span className="ident">{preview.verdict_hash}</span>
          {preview.rule_pack_version && <> · rules {preview.rule_pack_version}</>}
        </div>
      )}

      <H2>What recording writes</H2>
      <ul style={{ fontSize: 13, color: "var(--color-ink-muted)", lineHeight: 1.6, marginTop: 0 }}>
        {preview.will_record.map((w) => (
          <li key={w}>{w}</li>
        ))}
      </ul>
      <p style={{ fontSize: 12, color: "var(--color-ink-faint)" }}>{preview.recorded_meaning}</p>

      {/* The commit — the Approvals typed-confirm pattern, applied to a statutory record. */}
      <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--color-border)" }}>
        <label
          htmlFor={`file-confirm-${item.id}`}
          style={{
            fontSize: 13,
            lineHeight: 1.55,
            color: "var(--color-ink-muted)",
            display: "block",
          }}
        >
          This writes the filing record and a permanent, hash-chained audit entry sealing the
          figures above. The confirmation is bound to this exact preview — if the inputs or the
          computed figures change, the server refuses it. To confirm you have read the figures,
          type <strong className="ident">{preview.confirm_phrase}</strong>.
        </label>
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <input
            id={`file-confirm-${item.id}`}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={preview.confirm_phrase}
            autoComplete="off"
            disabled={!preview.can_confirm}
            style={{ ...input(), fontFamily: "var(--font-mono)", minWidth: 180 }}
          />
          <button
            type="button"
            disabled={reason !== null || record.isPending}
            onClick={() => record.mutate()}
            style={btn(reason === null && !record.isPending, "var(--color-accent)")}
          >
            {record.isPending ? "Recording…" : "Record as filed"}
          </button>
          <button type="button" onClick={onRePreview} style={btn(true, "transparent")}>
            Change the figures
          </button>
        </div>
        {reason && (
          <div style={{ color: "var(--color-ink-faint)", fontSize: 12, marginTop: 6 }}>{reason}</div>
        )}
        {record.error != null && <RecordFailure error={record.error} phrase={preview.confirm_phrase} />}
      </div>
    </div>
  );
}

/** 4-question template for a failed RECORD — with the precision a refusing server allows
 *  (mirrors Approvals.WriteFailure: a 4xx/5xx answer means nothing was written). */
function RecordFailure({ error, phrase }: { error: unknown; phrase: string }) {
  const status = error instanceof ApiError ? error.status : null;
  const what =
    status === 409
      ? "The confirmation belonged to a different preview — the figures were recomputed and did not match, so the server refused to record."
      : status === 400
        ? "The typed confirmation did not match, so nothing was written."
        : status === 403
          ? "Your role is not permitted to record a statutory filing (Owner/Admin only)."
          : status !== null
            ? `The server refused this record (${status}).`
            : "The request failed before we got an answer back.";
  const safe =
    status !== null
      ? "Yes. The server answered and refused — no filing was recorded and nothing was submitted to any portal."
      : "We can't confirm either way, so we won't claim it. Nothing was submitted to a portal. Check the audit trail for a filing.recorded entry before retrying.";
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
        <strong style={{ fontWeight: 600 }}>Is your money and filing safe.</strong> {safe}
      </div>
      <div>
        <strong style={{ fontWeight: 600 }}>What to do next.</strong>{" "}
        {status === 409
          ? "Re-run the preview, read the fresh figures, and confirm those."
          : status === 400
            ? `Type ${phrase} exactly, then record again.`
            : "Open the Audit Room and check for a filing.recorded entry before retrying. If it isn't there, retry is safe."}
      </div>
      <div className="ident" style={{ color: "var(--color-ink-faint)", marginTop: 4 }}>
        ref record-{phrase}-{status ?? "no-response"}
      </div>
    </div>
  );
}

/** T5: a persistent receipt (never a toast) + the attempt-evidence download. */
function ReceiptCard({ receipt, onBack }: { receipt: FilingReceipt; onBack: () => void }) {
  const [evErr, setEvErr] = useState(false);
  const download = async () => {
    setEvErr(false);
    try {
      const data = await api<unknown>("/filings/evidence");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `filing-attempt-evidence-${receipt.timestamp.slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setEvErr(true);
    }
  };
  return (
    <div
      style={{
        border: "1px solid var(--color-verify)",
        background: "var(--color-surface)",
        borderRadius: 8,
        padding: "16px 18px",
        fontSize: 13,
        lineHeight: 1.6,
      }}
    >
      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <strong style={{ fontWeight: 600 }}>Recorded.</strong>
        <VerifyChip state={receipt.verdict_hash ? "verified" : "honest_pending"} />
      </div>
      {/* T5 — the honest sentence, from the server, verbatim. */}
      <p style={{ margin: "8px 0", color: "var(--color-ink-muted)" }}>{receipt.label}</p>
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
      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
        <button type="button" onClick={download} style={btn(true, "var(--color-accent)")}>
          Download attempt evidence
        </button>
        <button type="button" onClick={onBack} style={btn(true, "transparent")}>
          Back to the queue
        </button>
      </div>
      {evErr && (
        <div style={{ color: "var(--color-verify-unbacked)", fontSize: 12, marginTop: 6 }}>
          The evidence bundle could not be fetched just now — your filing record stands; retry the
          download from this screen or the Audit Room.
        </div>
      )}
      <p style={{ color: "var(--color-ink-faint)", fontSize: 12, marginTop: 10, marginBottom: 0 }}>
        The evidence bundle (timestamps, figures shown, verdict hashes, trace ids — all sealed on
        the audit chain) is what you attach to a penalty-waiver request if the portal was down.
      </p>
    </div>
  );
}

// ── shared bits ──────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "block", fontSize: 12, color: "var(--color-ink-muted)" }}>
      {label}
      <div style={{ marginTop: 4 }}>{children}</div>
    </label>
  );
}

function card(): React.CSSProperties {
  return {
    background: "var(--color-surface)",
    border: "1px solid var(--color-border)",
    borderRadius: 8,
    padding: "16px 18px",
    marginTop: 12,
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
