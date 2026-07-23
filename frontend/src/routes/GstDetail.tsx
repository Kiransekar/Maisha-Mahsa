// P2-2 — GST deep flows, rendered inside /domains/gst (Domain.tsx mounts this for gst only).
//
// Mirrors api/app/web/api_gst.py exactly — read that file before changing these shapes.
//
// Honesty rules carried over from the rest of the SPA:
//   · Every figure arrives pre-formatted (the canonical Python ₹ renderer) with a badge state;
//     the badge passes through the SAME `badge` gate Domain.tsx wires (honestState + mahsa_up),
//     so this panel cannot invent its own path to a ✓ (invariant 1/6).
//   · IMS is preview-then-confirm (invariant 9): the confirm re-POSTs exactly the rows the
//     server previewed WITH the server's preview token — no token, no confirm offered. The
//     server independently 409s a commit whose selection was never previewed.
//   · BLOCKED-CA is stated, never papered over: the IMS deemed-accept deadline and the QRMP/
//     CMP-08 statutory due dates are not CA-sourced yet, and the UI says so verbatim.
//   · WS9.3: the draft-IRN honesty label renders on the e-invoice artifact surface, verbatim
//     from the server (`draft_irn_label`) — locked by GstDetail.test.tsx.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, apiBlob, ApiError } from "../lib/api";
import { VerifiedNumber, VerifyChip, type VerifyState } from "../components/VerifiedNumber";
import { ErrorState } from "../components/ErrorState";
import { useTraceId } from "../lib/trace";

// ── shapes (mirror api_gst.py) ───────────────────────────────────────────────

export type GstFigure = { key: string; label: string; value: string; raw: unknown; state: string };

export type Mismatch = {
  id: number;
  invoice_number: string;
  gstin_supplier: string;
  invoice_date: string;
  kind: "books_not_in_2b" | "in_2b_not_claimed" | string;
  note: string;
  figure: GstFigure;
};

export type ImsInvoice = {
  id: string;
  state: string;
  itc_eligible: boolean;
  reason: string;
  invoice_number: string;
  gstin_supplier: string;
  invoice_date: string;
  figure: GstFigure;
};

export type Obligation = {
  form: string;
  kind: string;
  frequency: string;
  period: string;
  due_date: string | null;
  pending_ca: boolean;
};

export type GstDetailData = {
  as_of: string;
  recon: {
    figures: GstFigure[];
    rule_36_4: {
      rule_id: string;
      text: string;
      statute: string;
      section: string;
      itc_claimed_ratio: number;
    };
    mismatches: Mismatch[];
  };
  ims: {
    invoices: ImsInvoice[];
    eligible_itc_total: GstFigure;
    deadline_pending_ca: boolean;
    deadline_note: string;
  };
  obligations: {
    profile: string;
    profile_source: string;
    quarter: string[];
    obligations: Obligation[];
    due_dates_note: string;
  };
  can_export: boolean;
  draft_irn_label: string;
};

export type ImsPreviewRow = ImsInvoice & { current_state: string; will_state: string };

export type ImsPreview = {
  committed: boolean;
  action: string;
  rows: ImsPreviewRow[];
  skipped: { id: number; reason: string }[];
  eligible_itc_total_after: GstFigure;
  deadline_note: string;
  preview_token?: string;
};

// ── pure logic (tested in GstDetail.test.tsx) ────────────────────────────────

/** What a confirm may commit — or null if no confirm may be offered.
 *
 *  The confirm re-POSTs **exactly the rows the server previewed** with the server's own
 *  token, never the live selection: a row ticked after the preview would otherwise commit
 *  without ever having been shown (the silent-write failure preview-then-confirm exists to
 *  prevent). No token ⇒ no confirm, ever — the server mints tokens only on previews. */
export function imsConfirmPlan(
  p: ImsPreview | null,
): { action: string; ids: number[]; preview_token: string } | null {
  if (!p || p.committed || !p.preview_token || p.rows.length === 0) return null;
  return {
    action: p.action,
    ids: p.rows.map((r) => Number(r.id)),
    preview_token: p.preview_token,
  };
}

/** The "when" of an obligation. A missing statutory date is STATED (§0.6), never guessed. */
export function obligationWhen(o: Obligation): string {
  if (o.due_date) return `due ${o.due_date}`;
  return "statutory due date pending CA — not guessed";
}

// ── presentational pieces (hook-free, render-tested) ─────────────────────────

const CARD: React.CSSProperties = {
  border: "1px solid var(--color-border)",
  background: "var(--color-surface)",
  borderRadius: 4,
  padding: "7px 12px",
  marginBottom: 4,
  fontSize: 13,
};

function Heading({ children }: { children: React.ReactNode }) {
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

/** (a) GSTR-2B vs books: the reconcile_itc aggregates + every named mismatch, all badged. */
export function ReconPanel({
  recon,
  asOf,
  badge,
}: {
  recon: GstDetailData["recon"];
  asOf: string;
  badge: (s: string) => VerifyState;
}) {
  const r = recon.rule_36_4;
  return (
    <div>
      <Heading>ITC reconciliation — GSTR-2B vs books</Heading>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(232px, 1fr))",
          gap: 8,
        }}
      >
        {recon.figures.map((f) => (
          <VerifiedNumber
            key={f.key}
            label={f.label}
            value={f.value}
            state={badge(f.state)}
            asOf={asOf}
            working={{ inputs: [{ label: "Fact key", value: f.key }] }}
          />
        ))}
      </div>
      <p style={{ fontSize: 12, color: "var(--color-ink-muted)", margin: "8px 0" }}>
        {r.rule_id} · {r.statute}, {r.section}: {r.text}
      </p>
      {recon.mismatches.length === 0 ? (
        <p style={{ fontSize: 12, color: "var(--color-ink-faint)", margin: 0 }}>
          No mismatched register rows — books and GSTR-2B agree line by line.
        </p>
      ) : (
        recon.mismatches.map((m) => (
          <div key={m.id} style={{ ...CARD, display: "flex", gap: 12, flexWrap: "wrap" }}>
            <span>
              {m.invoice_number} · <span className="tnum">{m.gstin_supplier}</span> ·{" "}
              {m.invoice_date}
            </span>
            <span className="tnum">{m.figure.value}</span>
            <VerifyChip state={badge(m.figure.state)} />
            <span style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>{m.note}</span>
          </div>
        ))
      )}
    </div>
  );
}

/** (c) the IMS invoice list + the dry-run panel. Presentational — the container owns state. */
export function ImsPanel({
  ims,
  badge,
  selected,
  action,
  preview,
  busy,
  error,
  traceId,
  onToggle,
  onAction,
  onPreview,
  onConfirm,
}: {
  ims: GstDetailData["ims"];
  badge: (s: string) => VerifyState;
  selected: ReadonlySet<string>;
  action: "accept" | "reject";
  preview: ImsPreview | null;
  busy: boolean;
  error: unknown;
  traceId: string;
  onToggle: (id: string) => void;
  onAction: (a: "accept" | "reject") => void;
  onPreview: () => void;
  onConfirm: () => void;
}) {
  const plan = imsConfirmPlan(preview);
  return (
    <div>
      <Heading>IMS — inward invoices · {ims.invoices.length}</Heading>
      <p style={{ fontSize: 12, color: "var(--color-ink-muted)", margin: "0 0 8px" }}>
        {ims.deadline_note}
      </p>
      {ims.invoices.length === 0 ? (
        <p style={{ fontSize: 12, color: "var(--color-ink-faint)" }}>
          No inward invoices in the ITC register yet — an empty register, not a set of zeroes.
        </p>
      ) : (
        <>
          {ims.invoices.map((inv) => (
            <label key={inv.id} style={{ ...CARD, display: "flex", gap: 12, flexWrap: "wrap" }}>
              <input
                type="checkbox"
                checked={selected.has(inv.id)}
                onChange={() => onToggle(inv.id)}
                aria-label={`Select ${inv.invoice_number}`}
              />
              <span>
                {inv.invoice_number} · <span className="tnum">{inv.gstin_supplier}</span>
              </span>
              <span className="tnum">{inv.figure.value}</span>
              <VerifyChip state={badge(inv.figure.state)} />
              <span style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>
                {inv.state} — {inv.reason}
              </span>
            </label>
          ))}
          <div style={{ display: "flex", gap: 8, alignItems: "center", margin: "8px 0" }}>
            <select
              value={action}
              onChange={(e) => onAction(e.target.value as "accept" | "reject")}
              aria-label="IMS action"
              style={{ fontSize: 13, padding: "4px 8px" }}
            >
              <option value="accept">Accept (ITC eligible)</option>
              <option value="reject">Reject (ITC not eligible)</option>
            </select>
            <button
              type="button"
              disabled={busy || selected.size === 0}
              onClick={onPreview}
              style={{ fontSize: 13 }}
            >
              Preview — nothing changes yet
            </button>
          </div>
          {error !== null && error !== undefined && (
            <ErrorState error={error} traceId={traceId} onRetry={onPreview} />
          )}
          {preview && (
            <div style={{ ...CARD, borderColor: "var(--color-border-strong)" }}>
              {preview.rows.map((r) => (
                <div key={r.id} style={{ fontSize: 12 }}>
                  {r.invoice_number}: {r.current_state} → <strong>{r.will_state}</strong> ·{" "}
                  <span className="tnum">{r.figure.value}</span>
                </div>
              ))}
              {preview.skipped.map((s) => (
                <div key={s.id} style={{ fontSize: 12, color: "var(--color-ink-muted)" }}>
                  #{s.id}: {s.reason}
                </div>
              ))}
              <div style={{ fontSize: 12, margin: "6px 0" }}>
                Eligible ITC after: <span className="tnum">{preview.eligible_itc_total_after.value}</span>{" "}
                <VerifyChip state={badge(preview.eligible_itc_total_after.state)} />
              </div>
              {preview.committed ? (
                <p style={{ fontSize: 12, color: "var(--color-ink-muted)", margin: 0 }}>
                  Committed — dispositions above were recomputed by the IMS engine.
                </p>
              ) : plan ? (
                <button type="button" disabled={busy} onClick={onConfirm} style={{ fontSize: 13 }}>
                  Confirm {plan.action} for {plan.ids.length} invoice(s)
                </button>
              ) : null}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** (d) QRMP / CMP-08 obligation calendar, profile labeled, no guessed dates. */
export function ObligationsPanel({ obligations }: { obligations: GstDetailData["obligations"] }) {
  return (
    <div>
      <Heading>
        Filing obligations — {obligations.profile} profile · {obligations.quarter[0]} to{" "}
        {obligations.quarter[2]}
      </Heading>
      <p style={{ fontSize: 12, color: "var(--color-ink-muted)", margin: "0 0 8px" }}>
        Profile from {obligations.profile_source}. {obligations.due_dates_note}
      </p>
      {obligations.obligations.map((o, i) => (
        <div key={`${o.form}-${o.period}-${i}`} style={{ ...CARD, display: "flex", gap: 12 }}>
          <span>
            {o.form} · {o.frequency} · {o.period}
          </span>
          <span
            style={{
              color: o.pending_ca ? "var(--color-ink-muted)" : "var(--color-ink)",
              fontSize: 12,
            }}
          >
            {obligationWhen(o)}
          </span>
        </div>
      ))}
    </div>
  );
}

/** (b) artifact downloads — HIDDEN without export (T11: hidden, not disabled), and the WS9.3
 *  draft-IRN honesty label renders verbatim on the e-invoice surface. */
export function DownloadsPanel({
  canExport,
  draftIrnLabel,
  period,
  invoice,
  error,
  onPeriod,
  onInvoice,
  onDownload,
}: {
  canExport: boolean;
  draftIrnLabel: string;
  period: string;
  invoice: string;
  error: string | null;
  onPeriod: (v: string) => void;
  onInvoice: (v: string) => void;
  onDownload: (path: string, filename: string) => void;
}) {
  if (!canExport) return null;
  return (
    <div>
      <Heading>Return artifacts</Heading>
      <div style={{ ...CARD, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <label style={{ fontSize: 12 }}>
          GSTR-1 period{" "}
          <input
            type="month"
            value={period}
            onChange={(e) => onPeriod(e.target.value)}
            style={{ fontSize: 13 }}
          />
        </label>
        <button
          type="button"
          disabled={!period}
          onClick={() => onDownload(`/gst/gstr1.json?period=${encodeURIComponent(period)}`, `gstr1-${period}.json`)}
          style={{ fontSize: 13 }}
        >
          Download GSTR-1 JSON
        </button>
      </div>
      <div style={{ ...CARD, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <label style={{ fontSize: 12 }}>
          e-invoice for invoice no.{" "}
          <input
            type="text"
            value={invoice}
            placeholder="INV-1"
            onChange={(e) => onInvoice(e.target.value)}
            style={{ fontSize: 13 }}
          />
        </label>
        <button
          type="button"
          disabled={!invoice.trim()}
          onClick={() =>
            onDownload(
              `/gst/einvoice.json?invoice=${encodeURIComponent(invoice.trim())}`,
              `einvoice-${invoice.trim()}.json`,
            )
          }
          style={{ fontSize: 13 }}
        >
          Download e-invoice JSON
        </button>
        {/* WS9.3 — verbatim from the server; a self-computed IRN must never read as filed. */}
        <span style={{ fontSize: 12, color: "var(--color-money-out)" }}>{draftIrnLabel}</span>
      </div>
      {error && (
        <div style={{ color: "var(--color-money-out)", fontSize: 12, marginBottom: 6 }}>{error}</div>
      )}
    </div>
  );
}

// ── container ────────────────────────────────────────────────────────────────

export function GstDetail({ badge }: { badge: (s: string) => VerifyState }) {
  const traceId = useTraceId("gst-detail");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["gst-detail"],
    queryFn: () => api<GstDetailData>("/gst/detail"),
  });

  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [action, setAction] = useState<"accept" | "reject">("accept");
  const [preview, setPreview] = useState<ImsPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [imsError, setImsError] = useState<unknown>(null);
  const [period, setPeriod] = useState("");
  const [invoice, setInvoice] = useState("");
  const [dlError, setDlError] = useState<string | null>(null);

  if (isLoading && !data) {
    return <p style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>Loading GST detail…</p>;
  }
  if (error) return <ErrorState error={error} traceId={traceId} onRetry={refetch} />;
  if (!data) return null;

  const post = (body: object) =>
    api<ImsPreview>("/gst/ims/action", { method: "POST", body: JSON.stringify(body) });

  const runPreview = async () => {
    setBusy(true);
    setImsError(null);
    try {
      setPreview(await post({ action, ids: [...selected].map(Number), confirm: false }));
    } catch (e) {
      setImsError(e);
    } finally {
      setBusy(false);
    }
  };

  const runConfirm = async () => {
    const plan = imsConfirmPlan(preview);
    if (!plan) return; // no server preview ⇒ no commit path exists on this client
    setBusy(true);
    setImsError(null);
    try {
      setPreview(await post({ ...plan, confirm: true }));
      setSelected(new Set());
      void refetch();
    } catch (e) {
      setImsError(e);
    } finally {
      setBusy(false);
    }
  };

  const download = async (path: string, filename: string) => {
    setDlError(null);
    try {
      const blob = await apiBlob(path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setDlError(
        e instanceof ApiError && e.status === 404
          ? "No invoice with that number — nothing was generated."
          : "The download failed — nothing was changed; retry from this screen.",
      );
    }
  };

  return (
    <section>
      <ReconPanel recon={data.recon} asOf={data.as_of} badge={badge} />
      <DownloadsPanel
        canExport={data.can_export}
        draftIrnLabel={data.draft_irn_label}
        period={period}
        invoice={invoice}
        error={dlError}
        onPeriod={setPeriod}
        onInvoice={setInvoice}
        onDownload={(p, f) => void download(p, f)}
      />
      <ImsPanel
        ims={data.ims}
        badge={badge}
        selected={selected}
        action={action}
        preview={preview}
        busy={busy}
        error={imsError}
        traceId={traceId}
        onToggle={(id) => {
          setPreview(null); // a changed selection invalidates the shown dry-run
          setSelected((s) => {
            const next = new Set(s);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
          });
        }}
        onAction={(a) => {
          setPreview(null);
          setAction(a);
        }}
        onPreview={() => void runPreview()}
        onConfirm={() => void runConfirm()}
      />
      <ObligationsPanel obligations={data.obligations} />
    </section>
  );
}
