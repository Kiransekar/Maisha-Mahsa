// WS7 — the Audit Room, the CA's default landing (app/core/landing.py ROLE_LANDING.CA).
// Reads GET /api/audit (app/web/api_domains.py::audit_json) — a pure re-derivation, never a
// re-verification done client side: `chain_intact` IS the server's `verify_chain(load_chain())`
// result, so this screen can never show a green chip over a chain the server itself flagged.
//
// This screen's whole job (per the ticket) is to let a CA satisfy themselves nothing was
// altered. Design for scrutiny: hashes in mono, newest-first, paging, and a chain-verification
// result that is unmissable — especially, ONLY especially, when it fails. A quietly-rendered
// tamper failure is worse than no audit log at all, so a broken chain gets the loudest, largest,
// most structurally distinct treatment on the page — not a small chip alongside the good state.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiBlob, ApiError } from "../lib/api";
import { ErrorState } from "../components/ErrorState";
import { inrPrecise } from "../components/BankCsvImport";
import { useTraceId } from "../lib/trace";
import { Header, H2, Empty } from "./Today";

export type AuditEntry = {
  timestamp: string;
  action: string;
  domain: string;
  user_id: string;
  query: string | null;
  validation_status: string;
  rules_version: string | null;
  prev_hash: string;
  this_hash: string;
};

type AuditData = {
  chain_intact: boolean;
  total: number;
  limit: number;
  offset: number;
  entries: AuditEntry[];
};

// ── pure logic (tested in AuditRoom.test.ts) ─────────────────────────────────

export type ChainBanner = {
  tone: "intact" | "broken";
  headline: string;
  detail: string;
};

/** The single honesty gate on this screen: the tone can ONLY come from the server's own
 *  `chain_intact` result, never re-derived or softened here. */
export function chainBanner(intact: boolean, total: number): ChainBanner {
  if (!intact) {
    return {
      tone: "broken",
      headline: "CHAIN VERIFICATION FAILED",
      detail:
        "The hash chain does not reconstruct: at least one entry's hash no longer matches its predecessor. This means an entry was altered, deleted, or reordered after being sealed. Do not treat any figure on this system as verified until this is investigated.",
    };
  }
  return {
    tone: "intact",
    headline: "Chain verified",
    detail: `All ${total} entr${total === 1 ? "y" : "ies"} in the log were re-hashed just now and each one's hash correctly follows from its predecessor. Nothing here has been altered since it was sealed.`,
  };
}

/** Paging arithmetic for a page of `limit` starting at `offset`, out of `total`. Pulled out so
 *  the off-by-one at the edges (empty log, partial last page) is tested, not eyeballed. */
export function pageInfo(total: number, limit: number, offset: number) {
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  return {
    from,
    to,
    hasPrev: offset > 0,
    hasNext: offset + limit < total,
    prevOffset: Math.max(0, offset - limit),
    nextOffset: offset + limit,
  };
}

// ── P1-2 CA query threads + sampling + pack downloads (WS8.2 parity) ─────────

export type ThreadEvent = {
  timestamp: string;
  event: string;
  user_id: string;
  note: string | null;
  doc_id: string | null;
  audit_hash: string; // the seal ref on the ONE hash chain
};

export type CaThread = {
  id: number;
  created_at: string;
  domain: string;
  entry_ref: string;
  question: string;
  state: string; // open -> responded -> resolved
  raised_by: string;
  events: ThreadEvent[];
};

export type ThreadsData = {
  threads: CaThread[];
  // The caller's OWN capabilities, computed by the server (api_domains.threads_json) — the SPA
  // never guesses a role client-side (same convention as payroll's can_confirm).
  can_respond: boolean;
  respond_denied_reason: string | null;
  can_export: boolean;
};

/** Which controls a thread offers this caller. Enabled/disabled-with-reason comes ONLY from the
 *  payload's server-computed capability — a missing reason gets an honest default, never an
 *  enabled button. Resolve needs view_audit, which every viewer of this screen holds (the GET
 *  is gated on it), but only a *responded* thread may resolve (server rule, mirrored). */
export function threadGates(
  state: string,
  canRespond: boolean,
  deniedReason: string | null,
): { showRespond: boolean; respondDisabledReason: string | null; showResolve: boolean } {
  const answerable = state !== "resolved";
  return {
    showRespond: answerable && canRespond,
    respondDisabledReason:
      answerable && !canRespond
        ? (deniedReason ?? "your role cannot respond (write capability required)")
        : null,
    showResolve: state === "responded",
  };
}

export function threadChip(state: string): { label: string; color: string } {
  if (state === "open") return { label: "open — awaiting response", color: "var(--color-warn)" };
  if (state === "responded")
    return { label: "responded — awaiting CA resolve", color: "var(--color-verify-pending)" };
  if (state === "resolved") return { label: "resolved", color: "var(--color-verify)" };
  return { label: state, color: "var(--color-ink-muted)" }; // unknown state shown verbatim, never hidden
}

export type SampleSpec = { date_from: string; date_to: string; n: number; domain: string };

/** Query string for GET /api/audit/sample — pure so the param mapping is tested, not eyeballed. */
export function sampleQueryString(f: SampleSpec): string {
  const p = new URLSearchParams({ date_from: f.date_from, date_to: f.date_to, n: String(f.n) });
  if (f.domain.trim()) p.set("domain", f.domain.trim());
  return p.toString();
}

export type SampleVoucher = {
  voucher_id: number;
  entry_date: string;
  reference: string | null;
  description: string | null;
  source: string | null;
  total_debit_paise: number;
  total_credit_paise: number;
  documents: { doc_id: string; file_name: string; doc_type: string }[];
};

export type SampleData = {
  spec: { domain: string | null; date_from: string; date_to: string; n: number };
  seed: string;
  population: number;
  sample: SampleVoucher[];
};

const INPUT: React.CSSProperties = {
  border: "1px solid var(--color-border-strong)",
  borderRadius: 4,
  padding: "6px 8px",
  fontSize: 13,
  fontFamily: "inherit",
  background: "var(--color-surface)",
  color: "var(--color-ink)",
};

const BTN: React.CSSProperties = {
  background: "var(--color-accent)",
  color: "var(--color-on-accent)",
  border: "none",
  padding: "7px 14px",
  borderRadius: 4,
  fontSize: 13,
  cursor: "pointer",
  fontFamily: "inherit",
};

const CARD: React.CSSProperties = {
  border: "1px solid var(--color-border)",
  borderRadius: 8,
  padding: "12px 16px",
  marginBottom: 8,
  background: "var(--color-surface)",
};

const LABEL: React.CSSProperties = {
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: "var(--color-ink-faint)",
  display: "block",
  marginBottom: 2,
};

/** Pack downloads — rendered ONLY when the server says the caller holds `export` (T11: hidden,
 *  not disabled — an Approver must not even see that exportable packs exist here). */
export function PackDownloads({ canExport }: { canExport: boolean }) {
  const [err, setErr] = useState<string | null>(null);
  if (!canExport) return null;
  const download = async (path: string, filename: string) => {
    setErr(null);
    try {
      const blob = await apiBlob(path);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(
        e instanceof ApiError && e.status === 503
          ? "Mahsa is unreachable, so the pack cannot bind a rules version — nothing was generated or fabricated. Retry once Mahsa is back."
          : "The download failed — nothing was changed; retry from this screen.",
      );
    }
  };
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ ...LABEL, marginBottom: 0, display: "inline" }}>Audit pack</span>
        <button type="button" style={BTN} onClick={() => download("/audit/pack.zip", "audit_pack.zip")}>
          Download .zip (CSV registers)
        </button>
        <button type="button" style={BTN} onClick={() => download("/audit/pack.pdf", "audit_pack.pdf")}>
          Download .pdf
        </button>
      </div>
      {err && (
        <div style={{ color: "var(--color-money-out)", fontSize: 12, marginTop: 6 }}>{err}</div>
      )}
    </div>
  );
}

/** One thread — presentational (no queries), so the lifecycle states render-test cleanly. */
export function ThreadCard({
  thread,
  gates,
  onRespond,
  onResolve,
  busy,
  error,
  traceId,
}: {
  thread: CaThread;
  gates: ReturnType<typeof threadGates>;
  onRespond: (docId: string, note: string) => void;
  onResolve: () => void;
  busy: boolean;
  error: unknown;
  traceId: string;
}) {
  const [docId, setDocId] = useState("");
  const [note, setNote] = useState("");
  const chip = threadChip(thread.state);
  return (
    <div style={CARD}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <strong style={{ fontSize: 14 }}>{thread.question}</strong>
          <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginTop: 2 }}>
            {thread.domain} · entry <span className="ident">{thread.entry_ref}</span> · raised by{" "}
            {thread.raised_by} · {thread.created_at}
          </div>
        </div>
        <span style={{ color: chip.color, fontSize: 12, whiteSpace: "nowrap" }}>● {chip.label}</span>
      </div>

      <div style={{ marginTop: 8 }}>
        {thread.events.map((ev) => (
          <div
            key={ev.audit_hash}
            style={{ fontSize: 12, color: "var(--color-ink-muted)", marginTop: 4 }}
          >
            <strong>{ev.event}</strong> · {ev.timestamp} · by {ev.user_id}
            {ev.note && <> · “{ev.note}”</>}
            {ev.doc_id && (
              <>
                {" "}
                · doc <span className="ident">{ev.doc_id}</span>
              </>
            )}
            <div style={{ fontSize: 11, color: "var(--color-ink-faint)" }}>
              seal <span className="ident">{ev.audit_hash}</span>
            </div>
          </div>
        ))}
      </div>

      {gates.showRespond && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onRespond(docId, note);
          }}
          style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap", alignItems: "end" }}
        >
          <span>
            <span style={LABEL}>Vault document id (the evidence)</span>
            <input
              style={{ ...INPUT, width: 280 }}
              value={docId}
              onChange={(e) => setDocId(e.target.value)}
              required
            />
          </span>
          <span>
            <span style={LABEL}>Note</span>
            <input style={{ ...INPUT, width: 220 }} value={note} onChange={(e) => setNote(e.target.value)} />
          </span>
          <button type="submit" style={BTN} disabled={busy || !docId.trim()}>
            Respond with document
          </button>
        </form>
      )}
      {gates.respondDisabledReason && (
        <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginTop: 10 }}>
          <button type="button" disabled style={{ ...pagerBtn(false), cursor: "not-allowed" }}>
            Respond with document
          </button>{" "}
          {gates.respondDisabledReason}
        </div>
      )}
      {gates.showResolve && (
        <div style={{ marginTop: 10 }}>
          <button type="button" style={BTN} disabled={busy} onClick={onResolve}>
            Resolve query
          </button>
        </div>
      )}
      {error != null && (
        <div style={{ marginTop: 10 }}>
          <ErrorState error={error} traceId={traceId} operation="write" />
        </div>
      )}
    </div>
  );
}

function ThreadItem({ thread, data }: { thread: CaThread; data: ThreadsData }) {
  const qc = useQueryClient();
  const traceId = useTraceId(`audit-thread-${thread.id}`);
  const gates = threadGates(thread.state, data.can_respond, data.respond_denied_reason);
  const invalidate = () => {
    // Every transition seals onto the ONE chain, so the log below must refresh too.
    qc.invalidateQueries({ queryKey: ["audit-threads"] });
    qc.invalidateQueries({ queryKey: ["audit"] });
  };
  const respond = useMutation({
    mutationFn: (v: { doc_id: string; note: string }) =>
      api(`/audit/threads/${thread.id}/respond`, { method: "POST", body: JSON.stringify(v) }),
    onSuccess: invalidate,
  });
  const resolve = useMutation({
    mutationFn: () =>
      api(`/audit/threads/${thread.id}/resolve`, { method: "POST", body: JSON.stringify({}) }),
    onSuccess: invalidate,
  });
  return (
    <ThreadCard
      thread={thread}
      gates={gates}
      busy={respond.isPending || resolve.isPending}
      error={respond.error ?? resolve.error}
      traceId={traceId}
      onRespond={(doc_id, note) => respond.mutate({ doc_id, note })}
      onResolve={() => resolve.mutate()}
    />
  );
}

function RaiseForm() {
  const qc = useQueryClient();
  const traceId = useTraceId("audit-thread-raise");
  const [domain, setDomain] = useState("");
  const [entryRef, setEntryRef] = useState("");
  const [question, setQuestion] = useState("");
  const raise = useMutation({
    mutationFn: () =>
      api("/audit/threads", {
        method: "POST",
        body: JSON.stringify({ domain, entry_ref: entryRef, question }),
      }),
    onSuccess: () => {
      setDomain("");
      setEntryRef("");
      setQuestion("");
      qc.invalidateQueries({ queryKey: ["audit-threads"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });
  return (
    <div style={{ ...CARD, marginBottom: 16 }}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          raise.mutate();
        }}
        style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "end" }}
      >
        <span>
          <span style={LABEL}>Domain</span>
          <input
            style={{ ...INPUT, width: 120 }}
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="e.g. ledger"
            required
          />
        </span>
        <span>
          <span style={LABEL}>Entry / figure ref</span>
          <input
            style={{ ...INPUT, width: 180 }}
            value={entryRef}
            onChange={(e) => setEntryRef(e.target.value)}
            placeholder="e.g. journal:14"
            required
          />
        </span>
        <span style={{ flex: 1, minWidth: 240 }}>
          <span style={LABEL}>Question</span>
          <input
            style={{ ...INPUT, width: "100%" }}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            required
          />
        </span>
        <button
          type="submit"
          style={BTN}
          disabled={raise.isPending || !domain.trim() || !entryRef.trim() || !question.trim()}
        >
          Raise query
        </button>
      </form>
      <div style={{ color: "var(--color-ink-faint)", fontSize: 11, marginTop: 6 }}>
        The raise is sealed onto the audit chain — it cannot be silently withdrawn later.
      </div>
      {raise.error != null && (
        <div style={{ marginTop: 10 }}>
          <ErrorState error={raise.error} traceId={traceId} operation="write" />
        </div>
      )}
    </div>
  );
}

/** Shares the ["audit-threads"] query (react-query dedupes by key — one fetch) so the download
 *  row's visibility comes from the SAME server-computed capability the threads use. Fail-closed:
 *  no payload yet -> hidden. */
function PackDownloadsGate() {
  const { data } = useQuery({
    queryKey: ["audit-threads"],
    queryFn: () => api<ThreadsData>("/audit/threads"),
  });
  return <PackDownloads canExport={data?.can_export === true} />;
}

function ThreadsSection() {
  const traceId = useTraceId("audit-threads");
  const { data, error, refetch } = useQuery({
    queryKey: ["audit-threads"],
    queryFn: () => api<ThreadsData>("/audit/threads"),
  });
  return (
    <>
      <H2>CA query threads</H2>
      <RaiseForm />
      {error != null && <ErrorState error={error} traceId={traceId} onRetry={refetch} />}
      {data &&
        (data.threads.length === 0 ? (
          <Empty>No queries have been raised yet.</Empty>
        ) : (
          data.threads.map((t) => <ThreadItem key={t.id} thread={t} data={data} />)
        ))}
    </>
  );
}

/** The sample result — presentational, exported for tests. Money is paise-exact (inrPrecise);
 *  the seed is shown because determinism is the point: same spec, same org, same sample. */
export function SampleResult({ data }: { data: SampleData }) {
  return (
    <div style={{ ...CARD, marginTop: 8 }}>
      <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginBottom: 8 }}>
        Deterministic sample — re-running this exact spec reproduces it. Seed{" "}
        <span className="ident">{data.seed}</span> · {data.sample.length} of {data.population}{" "}
        vouchers in range
      </div>
      {data.sample.length === 0 ? (
        <Empty>No vouchers in the population match this spec.</Empty>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
            <thead>
              <tr>
                {["Voucher", "Date", "Reference", "Description", "Source", "Debit", "Credit", "Documents"].map(
                  (h) => (
                    <th
                      key={h}
                      style={{
                        textAlign: h === "Debit" || h === "Credit" ? "right" : "left",
                        ...LABEL,
                        padding: "4px 8px",
                        borderBottom: "1px solid var(--color-border-strong)",
                      }}
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {data.sample.map((v) => (
                <tr key={v.voucher_id}>
                  <td className="tnum" style={{ padding: "4px 8px" }}>
                    {v.voucher_id}
                  </td>
                  <td className="tnum" style={{ padding: "4px 8px" }}>
                    {v.entry_date}
                  </td>
                  <td style={{ padding: "4px 8px" }}>{v.reference ?? "—"}</td>
                  <td style={{ padding: "4px 8px" }}>{v.description ?? "—"}</td>
                  <td style={{ padding: "4px 8px" }}>{v.source ?? "—"}</td>
                  <td className="tnum" style={{ padding: "4px 8px", textAlign: "right" }}>
                    {inrPrecise(v.total_debit_paise)}
                  </td>
                  <td className="tnum" style={{ padding: "4px 8px", textAlign: "right" }}>
                    {inrPrecise(v.total_credit_paise)}
                  </td>
                  <td style={{ padding: "4px 8px" }}>
                    {v.documents.length === 0 ? (
                      <span style={{ color: "var(--color-ink-muted)" }}>
                        no vault documents linked
                      </span>
                    ) : (
                      v.documents.map((d) => (
                        <div key={d.doc_id} style={{ fontSize: 12 }}>
                          {d.file_name} ({d.doc_type}) · <span className="ident">{d.doc_id}</span>
                        </div>
                      ))
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function SampleSection() {
  const traceId = useTraceId("audit-sample");
  const [form, setForm] = useState<SampleSpec>({ date_from: "", date_to: "", n: 10, domain: "" });
  const [spec, setSpec] = useState<SampleSpec | null>(null);
  const { data, error, refetch } = useQuery({
    queryKey: ["audit-sample", spec],
    queryFn: () => api<SampleData>(`/audit/sample?${sampleQueryString(spec!)}`),
    enabled: spec !== null,
  });
  return (
    <>
      <H2>Voucher sampling</H2>
      <div style={CARD}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setSpec({ ...form });
          }}
          style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "end" }}
        >
          <span>
            <span style={LABEL}>From</span>
            <input
              type="date"
              style={INPUT}
              value={form.date_from}
              onChange={(e) => setForm({ ...form, date_from: e.target.value })}
              required
            />
          </span>
          <span>
            <span style={LABEL}>To</span>
            <input
              type="date"
              style={INPUT}
              value={form.date_to}
              onChange={(e) => setForm({ ...form, date_to: e.target.value })}
              required
            />
          </span>
          <span>
            <span style={LABEL}>Sample size</span>
            <input
              type="number"
              min={1}
              max={200}
              style={{ ...INPUT, width: 90 }}
              value={form.n}
              onChange={(e) => setForm({ ...form, n: Number(e.target.value) })}
              required
            />
          </span>
          <span>
            <span style={LABEL}>Domain (optional)</span>
            <input
              style={{ ...INPUT, width: 120 }}
              value={form.domain}
              onChange={(e) => setForm({ ...form, domain: e.target.value })}
              placeholder="all"
            />
          </span>
          <button type="submit" style={BTN} disabled={!form.date_from || !form.date_to}>
            Draw sample
          </button>
        </form>
      </div>
      {error != null && <ErrorState error={error} traceId={traceId} onRetry={refetch} />}
      {data && <SampleResult data={data} />}
    </>
  );
}

// ── screen ───────────────────────────────────────────────────────────────────

const PAGE_SIZE = 50;

export function AuditRoom() {
  const [offset, setOffset] = useState(0);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["audit", offset],
    queryFn: () => api<AuditData>(`/audit?limit=${PAGE_SIZE}&offset=${offset}`),
  });

  if (isLoading && !data) return <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>;

  if (error) {
    return (
      <div>
        <Header title="Audit Room" />
        <ErrorState error={error} traceId={`audit-${Date.now().toString(36)}`} onRetry={refetch} />
      </div>
    );
  }
  if (!data) return null;

  const banner = chainBanner(data.chain_intact, data.total);
  const page = pageInfo(data.total, data.limit, data.offset);

  return (
    <section>
      <Header title="Audit Room" />

      <ChainVerificationBanner banner={banner} />

      <PackDownloadsGate />
      <ThreadsSection />
      <SampleSection />

      <H2>
        Hash-chained log · {data.total} entr{data.total === 1 ? "y" : "ies"}
      </H2>

      {data.entries.length === 0 ? (
        <Empty>Nothing has been sealed to the audit chain yet.</Empty>
      ) : (
        <>
          <div style={{ color: "var(--color-ink-faint)", fontSize: 12, marginBottom: 8 }}>
            Newest first · showing {page.from}–{page.to} of {data.total}
          </div>
          {data.entries.map((e, i) => (
            <EntryRow key={`${e.this_hash}-${i}`} entry={e} />
          ))}
          <Pager
            page={page}
            onPrev={() => setOffset(page.prevOffset)}
            onNext={() => setOffset(page.nextOffset)}
          />
        </>
      )}
    </section>
  );
}

/** The most important element on the screen when the chain is broken — large, alone at the
 *  top, structurally distinct (not just a red chip) from every other surface in the product. */
function ChainVerificationBanner({ banner }: { banner: ChainBanner }) {
  const broken = banner.tone === "broken";
  return (
    <div
      role={broken ? "alert" : undefined}
      style={{
        border: `1px solid ${broken ? "var(--color-verify-unbacked)" : "var(--color-verify)"}`,
        borderLeft: `5px solid ${broken ? "var(--color-verify-unbacked)" : "var(--color-verify)"}`,
        background: broken ? "var(--color-verify-unbacked)" : "var(--color-surface)",
        color: broken ? "#fff" : "var(--color-ink)",
        borderRadius: 8,
        padding: broken ? "20px 22px" : "14px 16px",
        marginBottom: 20,
      }}
    >
      <div
        style={{
          fontSize: broken ? 20 : 15,
          fontWeight: 500,
          letterSpacing: broken ? "0.02em" : "-0.01em",
        }}
      >
        {broken ? "⚠ " : "✓ "}
        {banner.headline}
      </div>
      <div
        style={{
          fontSize: 13,
          lineHeight: 1.55,
          marginTop: 6,
          color: broken ? "rgba(255,255,255,0.92)" : "var(--color-ink-muted)",
        }}
      >
        {banner.detail}
      </div>
    </div>
  );
}

function EntryRow({ entry }: { entry: AuditEntry }) {
  return (
    <div
      style={{
        border: "1px solid var(--color-border)",
        borderRadius: 8,
        padding: "12px 16px",
        marginBottom: 8,
        background: "var(--color-surface)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <strong style={{ fontSize: 14 }}>{entry.action}</strong>
          <span style={{ color: "var(--color-ink-muted)", fontSize: 13 }}> · {entry.domain}</span>
        </div>
        <div className="tnum" style={{ color: "var(--color-ink-faint)", fontSize: 12 }}>
          {entry.timestamp}
        </div>
      </div>
      <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginTop: 4 }}>
        by {entry.user_id}
        {entry.query && <> · {entry.query}</>}
        {" · "}
        status {entry.validation_status || "—"}
        {entry.rules_version && <> · rules {entry.rules_version}</>}
      </div>
      <div style={{ fontSize: 11, marginTop: 8, color: "var(--color-ink-faint)" }}>
        <div>
          prev <span className="ident">{entry.prev_hash}</span>
        </div>
        <div>
          this <span className="ident">{entry.this_hash}</span>
        </div>
      </div>
    </div>
  );
}

function Pager({
  page,
  onPrev,
  onNext,
}: {
  page: ReturnType<typeof pageInfo>;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
      <button
        type="button"
        disabled={!page.hasPrev}
        onClick={onPrev}
        style={pagerBtn(page.hasPrev)}
      >
        ← Newer
      </button>
      <button
        type="button"
        disabled={!page.hasNext}
        onClick={onNext}
        style={pagerBtn(page.hasNext)}
      >
        Older →
      </button>
    </div>
  );
}

function pagerBtn(enabled: boolean): React.CSSProperties {
  return {
    background: "transparent",
    border: "1px solid var(--color-border-strong)",
    color: enabled ? "var(--color-ink)" : "var(--color-ink-faint)",
    padding: "6px 12px",
    borderRadius: 4,
    fontSize: 13,
    fontFamily: "inherit",
    cursor: enabled ? "pointer" : "not-allowed",
  };
}
