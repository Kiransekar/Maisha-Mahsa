// Exception Inbox (WS7.5) rebuilt in React. Reads /api/inbox — the same assembler the HTMX page
// renders. Five queues, ranked by ₹ impact, honest-empty where a source isn't wired yet.
//
// Bulk ops (research T3 + anti-pattern #3) are preview-then-confirm, never one-click:
// a bulk button POSTs /api/inbox/bulk with confirm=false, which is a pure dry-run, and renders
// the returned rows / skips / ₹ total. Only an explicit confirm on that preview re-POSTs with
// confirm=true and writes. There is no code path here that mutates on the first click.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { inrOrPending } from "../lib/money";
import { VerifyChip } from "../components/VerifiedNumber";
import { ErrorState } from "../components/ErrorState";
import { BulkPreview, bulkBlockReason, confirmPlan, type BulkPreviewData } from "../components/BulkPreview";
import { useTraceId } from "../lib/trace";
import { Empty, H2, Header, MahsaDownBanner } from "./Today";

type Item = {
  id: string;
  queue: string;
  what: string;
  when: string | null;
  impact_paise: number | null;
  impact_label: string;
  action_label: string;
  domain: string;
  selectable: boolean;
  detail: string;
  verify_state: string | null;
};
type Queue = {
  key: string;
  label: string;
  source: string | null;
  stub_note: string | null;
  empty: string;
  items: Item[];
};
type InboxData = { as_of: string; mahsa_up: boolean; queues: Queue[]; items: Item[] };

const BULK_BTN: React.CSSProperties = {
  background: "transparent",
  border: "1px solid var(--color-border-strong)",
  color: "var(--color-ink)",
  padding: "6px 12px",
  borderRadius: 4,
  fontSize: 13,
  fontFamily: "inherit",
  cursor: "pointer",
};

export function Inbox() {
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["inbox"],
    queryFn: () => api<InboxData>("/inbox"),
  });

  const traceId = useTraceId("inbox");
  const bulkTraceId = useTraceId("inbox-bulk");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<BulkPreviewData | null>(null);

  // The ids are an explicit argument, never read from live state inside the mutation. A confirm
  // passes the ids the SERVER previewed (confirmPlan), so what commits is exactly what was shown.
  const bulk = useMutation({
    mutationFn: (vars: { action: string; ids: string[]; confirm: boolean }) =>
      api<BulkPreviewData>("/inbox/bulk", {
        method: "POST",
        body: JSON.stringify({ action: vars.action, ids: vars.ids, confirm: vars.confirm }),
      }),
    onSuccess: (res) => {
      setPreview(res);
      // Only a real write invalidates: a dry-run changed nothing, so refetching would just
      // churn the list the user is mid-way through selecting from.
      if (res.committed) {
        setSelected(new Set());
        qc.invalidateQueries({ queryKey: ["inbox"] });
        qc.invalidateQueries({ queryKey: ["today"] });
      }
    },
  });

  // Selection is frozen while a preview is open — see the checkbox `disabled` below. Guarded here
  // too so no future caller can slip a row into the set behind an open preview.
  const toggle = (id: string) => {
    if (preview !== null) return; // frozen while a preview is open
    setSelected((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  };

  // The confirm re-POSTs the ids the SERVER previewed, never `selected`. No plan (Mahsa down, no
  // eligible row, or no action echoed) ⇒ no confirm handler ⇒ BulkPreview shows no confirm button.
  const confirmAction = (p: BulkPreviewData) => {
    const plan = confirmPlan(p);
    return plan ? () => bulk.mutate({ ...plan, confirm: true }) : undefined;
  };

  const closePreview = () => {
    setPreview(null);
    bulk.reset();
  };

  if (isLoading && !data) return <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>;
  if (error) {
    return (
      <div>
        <Header title="Exception Inbox" as_of={data?.as_of} />
        <ErrorState error={error} traceId={traceId} onRetry={refetch} />
      </div>
    );
  }
  if (!data) return null;

  const total = data.items.length;

  return (
    <section>
      <Header title="Exception Inbox" as_of={data.as_of} />
      <div style={{ color: "var(--color-ink-muted)", fontSize: 13, marginTop: -14 }}>
        {total === 0 ? "Nothing needs attention." : `${total} item(s) need attention.`}
      </div>
      {!data.mahsa_up && (
        <div style={{ marginTop: 16 }}>
          <MahsaDownBanner />
        </div>
      )}

      {/* The bulk bar. Both buttons are dry-runs — neither writes. */}
      {selected.size > 0 && !preview && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            flexWrap: "wrap",
            background: "var(--color-accent-sunk)",
            border: "1px solid var(--color-border-strong)",
            borderRadius: 8,
            padding: "10px 14px",
            margin: "18px 0 0",
            fontSize: 13,
          }}
        >
          <span className="tnum">{selected.size} selected</span>
          <button
            onClick={() => bulk.mutate({ action: "approve", ids: [...selected], confirm: false })}
            disabled={bulk.isPending}
            style={BULK_BTN}
          >
            Preview approve
          </button>
          <button
            onClick={() => bulk.mutate({ action: "reject", ids: [...selected], confirm: false })}
            disabled={bulk.isPending}
            style={BULK_BTN}
          >
            Preview reject
          </button>
          <button onClick={() => setSelected(new Set())} style={BULK_BTN}>
            Clear
          </button>
          <span style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>
            Nothing is written until you confirm the preview.
          </span>
        </div>
      )}

      {/* A failed CONFIRM is a WRITE: api_bulk.py commits per row, so it can partially succeed and
          must never claim "nothing was changed". A failed PREVIEW is a genuine dry-run read.
          `committed` is deliberately not passed: an HTTP failure carries no body, so the server
          reported no committed_count and we will not invent one. The partial-commit count that
          Mahsa's mid-write drop DOES report arrives as a 200 payload and is rendered by
          BulkPreview's mahsa_up:false branch. */}
      {bulk.error && (
        <div style={{ marginTop: 18 }}>
          <ErrorState
            error={bulk.error}
            traceId={bulkTraceId}
            operation={bulk.variables?.confirm ? "write" : "read"}
            onRetry={closePreview}
          />
        </div>
      )}

      {preview && (
        <div style={{ marginTop: 18 }}>
          <BulkPreview
            data={preview}
            busy={bulk.isPending}
            traceId={bulkTraceId}
            onConfirm={confirmAction(preview)}
            onCancel={closePreview}
          />
        </div>
      )}

      {data.queues.map((q) => (
        <div key={q.key}>
          <H2>
            {q.label}
            {q.items.length > 0 && (
              <span className="tnum" style={{ color: "var(--color-accent)" }}>
                {" "}
                · {q.items.length}
              </span>
            )}
          </H2>

          {q.items.length === 0 ? (
            <>
              <Empty>{q.empty}</Empty>
              {/* An unwired queue says so rather than looking like a genuine zero. */}
              {q.stub_note && (
                <div style={{ color: "var(--color-ink-faint)", fontSize: 11, margin: "6px 0 0" }}>
                  Source not wired yet — {q.stub_note}
                </div>
              )}
            </>
          ) : (
            q.items.map((it) => {
              // Null = bulk-actionable. Anything else is the reason shown in place of the box,
              // so a missing checkbox is never unexplained (T3).
              const blocked = bulkBlockReason(it);
              return (
              <div
                key={it.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: 16,
                  background: selected.has(it.id)
                    ? "var(--color-accent-sunk)"
                    : "var(--color-surface)",
                  border: "1px solid var(--color-border)",
                  borderRadius: 8,
                  padding: "12px 16px",
                  marginBottom: 8,
                }}
              >
                <div style={{ display: "flex", gap: 12, alignItems: "flex-start", minWidth: 0 }}>
                  {blocked === null && (
                    // Frozen while a preview is open: the confirm commits the previewed rows, so
                    // a row ticked now would create a selection the preview never showed.
                    <input
                      type="checkbox"
                      checked={selected.has(it.id)}
                      onChange={() => toggle(it.id)}
                      disabled={preview !== null}
                      aria-label={
                        preview !== null
                          ? `Selection is frozen while the bulk preview is open`
                          : `Select ${it.what} for a bulk decision`
                      }
                      style={{
                        marginTop: 4,
                        accentColor: "var(--color-accent)",
                        cursor: preview !== null ? "not-allowed" : "pointer",
                      }}
                    />
                  )}
                <div>
                  <strong>{it.what}</strong>
                  {blocked && (
                    <div style={{ color: "var(--color-ink-faint)", fontSize: 11 }}>
                      Not bulk-selectable — {blocked}
                    </div>
                  )}
                  {it.detail && (
                    <div style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>{it.detail}</div>
                  )}
                  <div
                    style={{
                      display: "flex",
                      gap: 12,
                      alignItems: "center",
                      flexWrap: "wrap",
                      marginTop: 4,
                    }}
                  >
                    <span className="tnum" style={{ fontSize: 13 }}>
                      {inrOrPending(it.impact_paise)}
                    </span>
                    <span style={{ color: "var(--color-ink-faint)", fontSize: 12 }}>
                      {it.impact_label}
                    </span>
                    {it.verify_state === "unbacked" && <VerifyChip state="unbacked" />}
                    {it.when && (
                      <span style={{ color: "var(--color-ink-faint)", fontSize: 12 }}>{it.when}</span>
                    )}
                  </div>
                </div>
                </div>
                <a
                  href={`/d/${it.domain}`}
                  style={{
                    border: "1px solid var(--color-border-strong)",
                    color: "var(--color-ink)",
                    padding: "7px 14px",
                    borderRadius: 4,
                    fontSize: 13,
                    textDecoration: "none",
                    whiteSpace: "nowrap",
                  }}
                >
                  {it.action_label}
                </a>
              </div>
              );
            })
          )}
        </div>
      ))}
    </section>
  );
}
