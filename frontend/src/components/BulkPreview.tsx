// Bulk preview-then-confirm panel (WS7.5 / research T3 + anti-pattern #3 — Xero's missing
// bulk-accept, 243 votes over 3+ years, the loudest single signal in the corpus).
//
// The contract this panel enforces:
//   · Nothing mutates on the first click. This renders the server's `confirm=false` dry-run.
//   · Every row that WILL change is named, with what exactly changes to it.
//   · Every row that will NOT change is named, with the specific reason it was skipped.
//   · The total ₹ impact is stated before the write — and is NEVER invented (invariant 2):
//     an unknown total says so rather than showing a confident ₹0.
//   · After the commit, the panel states the audit seal — a bulk write that doesn't say it was
//     sealed is indistinguishable from a silent bulk mutation.
//
// Shapes mirror api/app/web/api_bulk.py exactly. Read that file before changing these.

import { ErrorState } from "./ErrorState";
import { inr, inrOrPending } from "../lib/money";

export type BulkRow = {
  id: string;
  domain: string;
  what: string;
  impact_paise: number | null;
  will: string;
  reason?: string; // present on skipped rows only — always specific, never "not eligible"
};

export type BulkPreviewData = {
  mahsa_up: boolean;
  action: string | null;
  rows: BulkRow[];
  skipped: BulkRow[];
  total_impact_paise: number | null;
  unquantified_rows: number;
  committed: boolean;
  committed_count: number;
  note?: string;
  as_of?: string;
};

/**
 * What a confirm is allowed to commit — or null if no confirm may be offered at all.
 *
 * This is the whole point of preview-then-confirm: the confirm must re-POST **exactly the rows
 * the server previewed**, never the live selection. If the confirm sent the current selection,
 * a row ticked after the preview was rendered would be committed without ever having been shown
 * — a silent bulk write, which is the failure mode this panel exists to prevent.
 *
 * The action is likewise taken from the server's echo and never defaulted: defaulting an absent
 * verb to "approve" would let an unknown mutation resolve towards approving money.
 */
export function confirmPlan(data: BulkPreviewData): { action: string; ids: string[] } | null {
  if (!data.mahsa_up || data.committed) return null;
  if (!data.action) return null; // unknown verb ⇒ no confirm offered, never guessed
  if (data.rows.length === 0) return null;
  return { action: data.action, ids: data.rows.map((r) => r.id) };
}

/** The subset of an inbox item that decides whether it can be bulk-actioned. */
export type Selectable = { selectable: boolean; queue: string };

/**
 * Why this item cannot be bulk-actioned — or null if it can.
 *
 * This is the single client-side source of truth for "is the checkbox there", so a row can
 * never be silently un-selectable: whatever this returns non-null is shown to the user verbatim.
 * Mirrors `_skip_reason` in api/app/web/api_bulk.py; the server remains the authority and
 * re-states its own reason on the preview, so a drift here degrades to a skipped row, never to
 * an unintended write.
 */
export function bulkBlockReason(item: Selectable): string | null {
  if (item.queue === "mahsa_blocked")
    return "Mahsa's recompute did not match this figure. A blocked figure must be corrected, never bulk-waved through.";
  if (!item.selectable) return "This item is not eligible for a bulk decision.";
  if (item.queue !== "awaiting_approval")
    return `Bulk decisions apply only to items awaiting sign-off; this one is in '${item.queue}'.`;
  return null;
}

/**
 * The headline ₹ line shown before the user commits.
 *
 * Invariant 2: an unknown impact is never rendered as ₹0. The server sends
 * `total_impact_paise: null` when no eligible row carries a known amount; a real all-known
 * total of 0 arrives as 0 and is reported as a genuine zero.
 */
export function impactSummary(data: {
  total_impact_paise: number | null;
  unquantified_rows: number;
}): string {
  const unknown =
    data.unquantified_rows > 0
      ? ` · ${data.unquantified_rows} row(s) carry an impact we don't yet know — not counted above`
      : "";
  if (data.total_impact_paise === null)
    return `Total impact not yet known — we don't guess.${unknown}`;
  return `Total impact ${inr(data.total_impact_paise)}${unknown}`;
}

const CARD: React.CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border-strong)", // borders, not shadows (BRAND_THEME §3)
  borderRadius: 12,
  padding: "16px 18px",
  marginBottom: 18,
  fontSize: 13,
};

const CELL: React.CSSProperties = {
  borderBottom: "1px solid var(--color-border)",
  padding: "7px 10px 7px 0",
  textAlign: "left",
  verticalAlign: "top",
};

function Head({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 10,
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        color: "var(--color-ink-faint)",
        margin: "14px 0 4px",
      }}
    >
      {children}
    </div>
  );
}

function Btn({
  children,
  onClick,
  primary,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  primary?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        background: primary ? "var(--color-accent)" : "transparent",
        color: primary ? "var(--color-on-accent)" : "var(--color-ink)",
        fontWeight: 400, // hierarchy by size+tracking, never weight — browser default is bold
        border: primary ? "none" : "1px solid var(--color-border-strong)",
        padding: "7px 14px",
        borderRadius: 4,
        fontSize: 13,
        fontFamily: "inherit",
        cursor: disabled ? "default" : "pointer",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {children}
    </button>
  );
}

export function BulkPreview({
  data,
  busy,
  traceId,
  onConfirm,
  onCancel,
}: {
  data: BulkPreviewData;
  busy: boolean;
  /** Stable id so error-template question 4 is answerable (lib/trace.ts). */
  traceId: string;
  /** Undefined ⇒ no confirm may be offered (see confirmPlan). Never defaulted. */
  onConfirm?: () => void;
  onCancel: () => void;
}) {
  // Mahsa unreachable is stated prominently, never absorbed into a thinner panel (invariant 5),
  // and routed through the 4-question template so "what next" + the trace id are answered.
  //
  // We do NOT assert "this did not run": api_bulk.py's _mahsa_down carries committed_count, and
  // a mid-write drop leaves N decisions already sealed to the audit chain. The server's own note
  // is the authority on what happened; the client states it verbatim and never overrides it.
  if (!data.mahsa_up) {
    const partial = data.committed_count > 0;
    return (
      <ErrorState
        error={new Error(data.note ?? "Mahsa unreachable")}
        kind="mahsa_down"
        operation={partial ? "write" : "read"}
        committed={data.committed_count}
        traceId={traceId}
      >
        <div style={{ ...CARD, marginTop: 12, borderColor: "var(--color-verify-unbacked)" }}>
          <div
            style={{
              fontSize: 10,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              color: "var(--color-ink-faint)",
            }}
          >
            What the server reported
          </div>
          <p style={{ margin: "4px 0 12px", color: "var(--color-ink-muted)" }}>
            {data.note ??
              "Mahsa is unreachable. The server sent no further detail, so we are not going to guess at what did or did not run."}
          </p>
          {partial && (
            <p className="tnum" style={{ margin: "0 0 12px" }}>
              {data.committed_count} decision(s) were already sealed to the audit chain before
              Mahsa dropped. Those stand — check the audit trail before re-selecting anything.
            </p>
          )}
          <Btn onClick={onCancel}>Close</Btn>
        </div>
      </ErrorState>
    );
  }

  const verb = data.action === "reject" ? "rejected" : "approved";

  // Post-commit outcome. A bulk write that doesn't say it was sealed is indistinguishable
  // from a silent bulk mutation — so the audit seal is stated, not implied.
  if (data.committed) {
    return (
      <div style={{ ...CARD, borderColor: "var(--color-verify)" }}>
        <strong className="tnum">
          {data.committed_count} item(s) {verb}.
        </strong>
        <p style={{ margin: "6px 0 12px", color: "var(--color-ink-muted)" }}>
          {/* ponytail: plain text, not a link — the SPA has no /audit route yet and a dead link
              is worse than none. Make this an <a href="/audit"> the moment that route lands. */}
          Each decision was sealed onto the hash-chained audit log — it is now part of the
          permanent record and can be replayed from the audit trail. {impactSummary(data)}.
        </p>
        <Btn onClick={onCancel}>Done</Btn>
      </div>
    );
  }

  const nothingToDo = data.rows.length === 0;

  return (
    <div style={CARD}>
      <strong>
        Preview — nothing has changed yet. Confirm below to {data.action ?? "act on"}{" "}
        {data.rows.length} item(s).
      </strong>
      <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginTop: 4 }}>
        Your selection is frozen while this preview is open. Confirming commits exactly the rows
        listed here — nothing you tick afterwards can ride along.
      </div>

      {nothingToDo ? (
        <p style={{ margin: "6px 0 0", color: "var(--color-ink-muted)" }}>
          None of the selected items can take this action. Every one is listed below with the
          reason. Nothing was written.
        </p>
      ) : (
        <>
          <Head>Will change on confirm</Head>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.id}>
                  <td style={CELL}>
                    {r.what}
                    <div style={{ color: "var(--color-ink-faint)", fontSize: 11 }}>{r.domain}</div>
                  </td>
                  <td style={{ ...CELL, whiteSpace: "nowrap" }} className="tnum">
                    {r.impact_paise === null ? (
                      <span style={{ color: "var(--color-ink-faint)", fontSize: 11 }}>
                        not yet known
                      </span>
                    ) : (
                      inrOrPending(r.impact_paise)
                    )}
                  </td>
                  <td style={{ ...CELL, color: "var(--color-ink-muted)" }}>{r.will}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="tnum" style={{ marginTop: 10 }}>
            {impactSummary(data)}
          </div>
        </>
      )}

      {data.skipped.length > 0 && (
        <>
          <Head>Skipped — will not change</Head>
          {data.skipped.map((r) => (
            <div
              key={r.id}
              style={{
                borderBottom: "1px solid var(--color-border)",
                padding: "7px 0",
              }}
            >
              {r.what}
              <div style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>
                {r.reason ?? r.will}
              </div>
            </div>
          ))}
        </>
      )}

      <div
        style={{ display: "flex", gap: 12, marginTop: 16, alignItems: "center", flexWrap: "wrap" }}
      >
        {onConfirm ? (
          <Btn primary onClick={onConfirm} disabled={busy}>
            {busy ? "Sealing…" : `Confirm — ${data.action} ${data.rows.length} item(s)`}
          </Btn>
        ) : (
          !nothingToDo && (
            // The server did not echo a verb. Guessing it — the old `?? "approve"` — would resolve
            // an unknown mutation towards approving money. No confirm is offered at all.
            <span style={{ color: "var(--color-ink-muted)" }}>
              The server didn't name which action this preview is for, so there is nothing safe to
              confirm — we won't guess a verb that moves money. Cancel and preview again.
            </span>
          )
        )}
        <Btn onClick={onCancel} disabled={busy}>
          Cancel
        </Btn>
      </div>
    </div>
  );
}
