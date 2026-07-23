// P1-3 — owner-facing settings surface. First (and so far only) section: the CA seat —
// invite-by-email, the pending-invite list, and the "free + unlimited" entitlement fact
// (app/core/entitlements.SEAT_EXEMPT_ROLES — a backend TRUTH, stated here, not re-derived).
//
// RBAC: inviting (and seeing who's already invited) is Owner/Admin only — the SAME
// `manage_users` capability on both GET /api/ca/pending and POST /api/ca/invite
// (app/web/api_domains.py, WS8.3 + this ticket's addition). A caller without it gets a 403 on
// the very first load; that 403 IS the signal this screen renders as a disabled-with-reason
// banner (mirrors PayrollRun's `ConfirmFailure` — deriving the reason from the real server
// answer rather than a second, inventable copy of the role table).
//
// Accept happens on a separate route, /ca/accept (CaAccept.tsx) — that is the invited CA's own
// screen, signed in as themselves, not something an Owner drives from here.

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { ErrorState } from "../components/ErrorState";
import { ActionDrawer } from "../components/ActionDrawer";
import { useTraceId } from "../lib/trace";
import { Empty, H2, Header } from "./Today";
import { honestState, type ActionSpec } from "./Domain";

// ── types (server shapes from app/web/api_domains.py) ────────────────────────

export type PendingInvite = { membership_id: number; email: string; invited_at: string };
type PendingResponse = { invites: PendingInvite[] };
type InviteResponse = { membership_id: number; role: string; status: string; seat: string };

// ── WS10.1 Privacy types (server shapes from app/web/api_legal.py) ───────────

export type DpdpRequest = {
  id: number;
  requester: string;
  request_type: string;
  details: string | null;
  received_date: string;
  due_date: string;
  status: string;
  hold_basis: string | null;
  closed_date: string | null;
};
type DpdpResponse = { requests: DpdpRequest[]; sla_days: number; action: ActionSpec };
export type NoticeStatus = {
  doc_type: string;
  current_version: string | null;
  needs_acceptance: boolean;
};

// ── pure logic (tested in Settings.test.ts) ──────────────────────────────────

/** A 403 on the pending-list load IS the "you can't invite" signal — the same `manage_users`
 * gate the invite POST carries, checked earlier so the whole section can explain itself instead
 * of only failing once someone tries to submit. Any other error is a real load failure, not a
 * permission story, and falls through to ErrorState. */
export function caSectionDeniedReason(error: unknown): string | null {
  if (error instanceof ApiError && error.status === 403) {
    return "Only Owner and Admin can invite a CA or see who's already been invited.";
  }
  return null;
}

/** Enable Send only for a plausible, non-empty address — the server is the real validator
 * (400 for anything it rejects); this just stops an empty-form submit. */
export function canSubmitInvite(email: string): boolean {
  const t = email.trim();
  return t.length > 2 && t.includes("@") && !t.includes(" ");
}

/** One honest line per rights request: its status and the date that matters for it. The
 * server's status lattice (open|held|completed, app/core/dpdp.py) is rendered verbatim —
 * an unknown future status falls through as itself, never re-interpreted. */
export function requestStatusLine(r: DpdpRequest): string {
  if (r.status === "completed") return `completed ${r.closed_date ?? ""}`.trim();
  if (r.status === "held") return `HELD — legal hold · SLA due ${r.due_date}`;
  if (r.status === "open") return `open · respond by ${r.due_date}`;
  return r.status;
}

/** The notice card's one line, or null to render nothing. null current_version = nothing is
 * published (every doc is still a counsel-gated draft) — saying nothing is the honest render,
 * never a fabricated "you're covered". */
export function noticeLine(n: NoticeStatus): string | null {
  if (n.current_version === null) return null;
  return n.needs_acceptance
    ? `DPDP notice ${n.current_version} is in force — you have not accepted it yet.`
    : `DPDP notice ${n.current_version} accepted.`;
}

/** The server's own refusal reasons (app/core/ca_seat.invite_ca), in words. */
export function inviteErrorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return "That person is already a member or already invited.";
    if (error.status === 400) return "That doesn't look like an email address.";
    if (error.status === 403) return "Your role cannot invite a CA (Owner/Admin only).";
  }
  return "The invite could not be sent — try again.";
}

// ── screen ───────────────────────────────────────────────────────────────────

export function Settings() {
  const traceId = useTraceId("settings");
  const qc = useQueryClient();
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["ca-pending"],
    queryFn: () => api<PendingResponse>("/ca/pending"),
  });

  const deniedReason = caSectionDeniedReason(error);

  return (
    <section>
      <Header title="Settings" />
      <H2>CA seat</H2>
      {isLoading && !data && !error ? (
        <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>
      ) : deniedReason ? (
        <p
          style={{
            fontSize: 13,
            lineHeight: 1.55,
            margin: 0,
            padding: "10px 12px",
            borderRadius: 4,
            border: "1px solid var(--color-verify-pending)",
            background: "var(--color-surface-sunk)",
            color: "var(--color-ink-muted)",
          }}
        >
          {deniedReason}
        </p>
      ) : error ? (
        <ErrorState error={error} traceId={traceId} onRetry={refetch} />
      ) : (
        <CaSeatSection
          invites={data?.invites ?? []}
          onInvited={() => qc.invalidateQueries({ queryKey: ["ca-pending"] })}
        />
      )}
      <MemorySection />
      <PrivacySection />
    </section>
  );
}

// ── MEM.P0-5 — Company memory: view/edit the CFO posture block + history (app/web/api_memory.py) ──

export type CfoBlock = { content: string; used: number; limit: number; audit_hash?: string };
type MemoryData = { profile: string; cfo: CfoBlock };
export type MemoryHistoryRow = {
  content: string;
  superseded_at: string;
  superseded_by: string;
  audit_seq: number | null;
};
type MemoryHistoryResponse = { history: MemoryHistoryRow[] };

/** The write routes (PUT/append) wear `manage_users` (Owner/Admin only, see api_memory.py);
 * read (this whole tab) is open to everyone with `read`, including a read-only CA. So there is
 * no proactive client-side role check here (ponytail: the CA-seat pattern derives its
 * disabled-reason from a denied LOAD — memory's GET never denies a reader) — a non-owner who
 * tries to save simply gets this text from the server's own 403, same precedent as
 * `inviteErrorText`. */
export function memoryWriteErrorText(error: unknown): string {
  if (error instanceof ApiError) {
    // 422 = the overflow reject, and its message is DYNAMIC (the exact char count) — the
    // server's own words, rendered verbatim, never a re-derived client sentence (§0.4).
    if (error.status === 422 && error.detail) return error.detail;
    if (error.status === 403) return "Only Owner and Admin can edit company memory.";
  }
  return "The change could not be saved — try again.";
}

/** One line naming the sealed audit event a history row is linked to (survey §7.7 — auditable
 * updates made visible). The Audit Room has no per-row deep link today, so this points at the
 * room itself; the event id is still shown so it can be matched against the visible chain. */
export function historyAuditLine(r: MemoryHistoryRow): string {
  return r.audit_seq != null ? `sealed · audit #${r.audit_seq}` : "sealed";
}

const memBoxStyle: React.CSSProperties = {
  border: "1px solid var(--color-border)",
  background: "var(--color-surface)",
  borderRadius: 4,
  padding: "10px 12px",
  fontSize: 13,
};

const memLabelStyle: React.CSSProperties = {
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  color: "var(--color-ink-faint)",
  marginBottom: 6,
};

function CharMeter({ used, limit }: { used: number; limit: number }) {
  const over = used > limit;
  return (
    <span
      className="tnum"
      style={{ fontSize: 12, color: over ? "var(--color-verify-unbacked)" : "var(--color-ink-faint)" }}
    >
      {used}/{limit} chars
    </span>
  );
}

export function MemorySection() {
  const traceId = useTraceId("settings-memory");
  const qc = useQueryClient();
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["memory"],
    queryFn: () => api<MemoryData>("/memory"),
  });
  const { data: history } = useQuery({
    queryKey: ["memory-history"],
    queryFn: () => api<MemoryHistoryResponse>("/memory/history"),
  });

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [appendLine, setAppendLine] = useState("");

  function invalidate() {
    qc.invalidateQueries({ queryKey: ["memory"] });
    qc.invalidateQueries({ queryKey: ["memory-history"] });
  }

  const save = useMutation({
    mutationFn: (content: string) =>
      api<CfoBlock>("/memory", { method: "PUT", body: JSON.stringify({ content }) }),
    onSuccess: () => {
      setEditing(false);
      invalidate();
    },
  });

  const append = useMutation({
    mutationFn: (line: string) =>
      api<CfoBlock>("/memory/append", { method: "POST", body: JSON.stringify({ line }) }),
    onSuccess: () => {
      setAppendLine("");
      invalidate();
    },
  });

  return (
    <div style={{ marginTop: 28 }}>
      <H2>Company memory</H2>
      {isLoading && !data && !error ? (
        <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>
      ) : error ? (
        <ErrorState error={error} traceId={traceId} onRetry={refetch} />
      ) : data ? (
        <>
          <p style={{ fontSize: 12, color: "var(--color-ink-muted)", lineHeight: 1.55, margin: "0 0 12px" }}>
            Steers how Maisha talks about your company — durable preferences only,{" "}
            <strong style={{ fontWeight: 600, color: "var(--color-ink)" }}>never a source of
            figures</strong>: every rupee on screen still comes from the books, not from this text.
          </p>

          <div style={memBoxStyle}>
            <div style={memLabelStyle}>Org profile — derived from your company records, always current</div>
            <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontFamily: "inherit" }}>
              {data.profile || "—"}
            </pre>
          </div>

          <div style={{ ...memBoxStyle, marginTop: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", ...memLabelStyle, marginBottom: 6 }}>
              <span>CFO posture</span>
              <CharMeter used={editing ? draft.length : data.cfo.used} limit={data.cfo.limit} />
            </div>

            {editing ? (
              <>
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={8}
                  style={{
                    width: "100%",
                    boxSizing: "border-box",
                    border: "1px solid var(--color-border-strong)",
                    borderRadius: 4,
                    background: "var(--color-surface)",
                    color: "var(--color-ink)",
                    padding: "6px 8px",
                    fontSize: 13,
                    fontFamily: "inherit",
                  }}
                />
                {save.error != null && (
                  <p style={{ color: "var(--color-verify-unbacked)", fontSize: 12, margin: "6px 0 0" }}>
                    {memoryWriteErrorText(save.error)}
                  </p>
                )}
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <button
                    type="button"
                    disabled={save.isPending}
                    onClick={() => save.mutate(draft)}
                    style={memButtonStyle(true)}
                  >
                    {save.isPending ? "Saving…" : "Save"}
                  </button>
                  <button
                    type="button"
                    disabled={save.isPending}
                    onClick={() => setEditing(false)}
                    style={memButtonStyle(false)}
                  >
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <>
                <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontFamily: "inherit" }}>
                  {data.cfo.content || "— nothing recorded yet"}
                </pre>
                <button
                  type="button"
                  onClick={() => {
                    setDraft(data.cfo.content);
                    setEditing(true);
                  }}
                  style={{ ...memButtonStyle(false), marginTop: 8 }}
                >
                  Edit
                </button>
              </>
            )}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              const line = appendLine.trim();
              if (line) append.mutate(line);
            }}
            style={{ display: "flex", gap: 8, marginTop: 10 }}
          >
            <input
              value={appendLine}
              onChange={(e) => setAppendLine(e.target.value)}
              placeholder="Add one durable fact…"
              style={{
                flex: "1 1 auto",
                padding: "8px 10px",
                borderRadius: 4,
                border: "1px solid var(--color-border-strong)",
                background: "var(--color-surface)",
                color: "var(--color-ink)",
                fontSize: 13,
                fontFamily: "inherit",
              }}
            />
            <button
              type="submit"
              disabled={append.isPending || appendLine.trim().length === 0}
              style={memButtonStyle(false)}
            >
              {append.isPending ? "Adding…" : "Add"}
            </button>
          </form>
          {append.error != null && (
            <p style={{ color: "var(--color-verify-unbacked)", fontSize: 12, margin: "6px 0 0" }}>
              {memoryWriteErrorText(append.error)}
            </p>
          )}

          <div style={{ marginTop: 20 }}>
            <H2>Memory history</H2>
            {history == null ? null : history.history.length === 0 ? (
              <Empty>No memory edits yet — every save or append is versioned here.</Empty>
            ) : (
              <div>
                {history.history.map((r, i) => (
                  <div
                    key={i}
                    className="tnum"
                    style={{
                      padding: "9px 12px",
                      marginBottom: 6,
                      borderRadius: 4,
                      border: "1px solid var(--color-border)",
                      background: "var(--color-surface)",
                      fontSize: 13,
                    }}
                  >
                    <pre style={{ margin: "0 0 6px", whiteSpace: "pre-wrap", fontFamily: "inherit" }}>
                      {r.content}
                    </pre>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        gap: 12,
                        fontSize: 12,
                        color: "var(--color-ink-faint)",
                      }}
                    >
                      <span>
                        superseded {r.superseded_at.slice(0, 10)} by {r.superseded_by}
                      </span>
                      <Link to="/audit" className="ident" style={{ color: "var(--color-accent)" }}>
                        {historyAuditLine(r)}
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

function memButtonStyle(primary: boolean): React.CSSProperties {
  return {
    border: `1px solid ${primary ? "var(--color-accent)" : "var(--color-border-strong)"}`,
    background: primary ? "var(--color-accent)" : "var(--color-surface)",
    color: primary ? "var(--color-on-accent)" : "var(--color-ink)",
    borderRadius: 4,
    padding: "6px 14px",
    fontSize: 13,
    fontFamily: "inherit",
    cursor: "pointer",
  };
}

// ── WS10.1 — Privacy: DPDP notice status + rights requests (list · raise · status) ────────────

/** The notice status/accept card. Also rendered on Onboarding (consent capture point) — ONE
 * component, so the two surfaces cannot disagree about what is in force. Renders nothing while
 * no notice is published (the honest state — every docs/legal/ document is a draft). */
export function DpdpNoticeCard() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["dpdp-notice"],
    queryFn: () => api<NoticeStatus>("/legal/notice"),
  });
  const accept = useMutation({
    mutationFn: () => api("/legal/notice/accept", { method: "POST", body: "{}" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dpdp-notice"] }),
  });

  const line = data ? noticeLine(data) : null;
  if (line === null) return null;
  return (
    <p
      style={{
        fontSize: 13,
        lineHeight: 1.55,
        margin: "0 0 14px",
        padding: "10px 12px",
        borderRadius: 4,
        border: "1px solid var(--color-border-strong)",
        background: "var(--color-surface-sunk)",
        color: "var(--color-ink)",
        display: "flex",
        justifyContent: "space-between",
        gap: 12,
        alignItems: "center",
      }}
    >
      <span>{line}</span>
      {data?.needs_acceptance && (
        <button
          type="button"
          disabled={accept.isPending}
          onClick={() => accept.mutate()}
          style={{
            background: "var(--color-accent)",
            color: "var(--color-on-accent)",
            border: "none",
            padding: "6px 14px",
            borderRadius: 4,
            fontSize: 13,
            fontFamily: "inherit",
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          {accept.isPending ? "Recording…" : "Accept notice"}
        </button>
      )}
    </p>
  );
}

export function DpdpRequestsList({ requests }: { requests: DpdpRequest[] }) {
  return requests.length === 0 ? (
    <Empty>
      No data-principal rights requests recorded. Access, correction and erasure requests raised
      below get a 90-day response deadline on the compliance calendar.
    </Empty>
  ) : (
    <div>
      {requests.map((r) => (
        <div
          key={r.id}
          className="tnum"
          style={{
            padding: "9px 12px",
            marginBottom: 6,
            borderRadius: 4,
            border: "1px solid var(--color-border)",
            background: "var(--color-surface)",
            fontSize: 13,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
            <span>
              #{r.id} · {r.request_type} · {r.requester}
            </span>
            <span
              style={{
                color:
                  r.status === "held"
                    ? "var(--color-verify-unbacked)"
                    : r.status === "completed"
                      ? "var(--color-ink-faint)"
                      : "var(--color-ink-muted)",
                fontSize: 12,
              }}
            >
              {requestStatusLine(r)}
            </span>
          </div>
          {r.hold_basis != null && (
            <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--color-ink-muted)" }}>
              {r.hold_basis}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

export function PrivacySection() {
  const traceId = useTraceId("settings-privacy");
  const qc = useQueryClient();
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["dpdp-requests"],
    queryFn: () => api<DpdpResponse>("/legal/dpdp/requests"),
  });

  return (
    <div style={{ marginTop: 28 }}>
      <H2>Privacy · DPDP</H2>
      <DpdpNoticeCard />
      {isLoading && !data && !error ? (
        <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>
      ) : error ? (
        <ErrorState error={error} traceId={traceId} onRetry={refetch} />
      ) : data ? (
        <div>
          <DpdpRequestsList requests={data.requests} />
          {/* The SAME preview→confirm drawer every domain write uses, against the server's own
              field schema (no client copy to drift). No Mahsa fold runs on this screen, so the
              badge gate is called fail-closed (mahsaUp=false): nothing here can render ✓. */}
          <ActionDrawer
            domain="compliance"
            a={data.action}
            badge={(s) => honestState(s, false)}
            onCommitted={() => qc.invalidateQueries({ queryKey: ["dpdp-requests"] })}
          />
        </div>
      ) : null}
    </div>
  );
}

// ── presentational (pure props, no hooks) — tested directly via renderToStaticMarkup ──────────

export function CaInviteForm({
  email,
  onEmailChange,
  onSubmit,
  submitting,
  errorText,
}: {
  email: string;
  onEmailChange: (v: string) => void;
  onSubmit: () => void;
  submitting: boolean;
  errorText: string | null;
}) {
  const canSubmit = canSubmitInvite(email) && !submitting;
  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--color-ink-muted)", lineHeight: 1.55, margin: "0 0 14px" }}>
        A CA seat is <strong style={{ fontWeight: 600, color: "var(--color-ink)" }}>free and
        unlimited</strong> — it never counts against your plan's seat count. Invite as many as
        your books need.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) onSubmit();
        }}
        style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10 }}
      >
        <input
          type="email"
          required
          value={email}
          onChange={(e) => onEmailChange(e.target.value)}
          placeholder="ca@theirfirm.in"
          style={{
            flex: "1 1 260px",
            padding: "8px 10px",
            borderRadius: 4,
            border: "1px solid var(--color-border-strong)",
            background: "var(--color-surface)",
            color: "var(--color-ink)",
            fontSize: 13,
            fontFamily: "inherit",
          }}
        />
        <button
          type="submit"
          disabled={!canSubmit}
          style={{
            background: canSubmit ? "var(--color-accent)" : "var(--color-surface-sunk)",
            color: canSubmit ? "var(--color-on-accent)" : "var(--color-ink-muted)",
            border: "none",
            padding: "8px 16px",
            borderRadius: 4,
            fontSize: 13,
            fontFamily: "inherit",
            cursor: canSubmit ? "pointer" : "not-allowed",
            whiteSpace: "nowrap",
          }}
        >
          {submitting ? "Sending…" : "Invite CA"}
        </button>
      </form>
      {errorText != null && (
        <p style={{ color: "var(--color-verify-unbacked)", fontSize: 12, margin: "0 0 14px" }}>
          {errorText}
        </p>
      )}
    </div>
  );
}

export function PendingInvitesList({ invites }: { invites: PendingInvite[] }) {
  return (
    <div>
      <H2>Pending invites · {invites.length}</H2>
      {invites.length === 0 ? (
        <Empty>No CA invites are pending. Invited seats show here until accepted.</Empty>
      ) : (
        <div>
          {invites.map((i) => (
            <div
              key={i.membership_id}
              className="tnum"
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 16,
                padding: "9px 12px",
                marginBottom: 6,
                borderRadius: 4,
                border: "1px solid var(--color-border)",
                background: "var(--color-surface)",
                fontSize: 13,
              }}
            >
              <span>{i.email}</span>
              <span style={{ color: "var(--color-ink-faint)", fontSize: 12 }}>
                invited {i.invited_at.slice(0, 10)} · pending
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── hooked (owns the mutation, composes the two presentational pieces above) ──────────────────

export function CaSeatSection({
  invites,
  onInvited,
}: {
  invites: PendingInvite[];
  onInvited: () => void;
}) {
  const [email, setEmail] = useState("");
  const invite = useMutation({
    mutationFn: (addr: string) =>
      api<InviteResponse>("/ca/invite", { method: "POST", body: JSON.stringify({ email: addr }) }),
    onSuccess: () => {
      setEmail("");
      onInvited();
    },
  });

  return (
    <div>
      <CaInviteForm
        email={email}
        onEmailChange={setEmail}
        onSubmit={() => invite.mutate(email.trim())}
        submitting={invite.isPending}
        errorText={invite.error != null ? inviteErrorText(invite.error) : null}
      />
      <PendingInvitesList invites={invites} />
    </div>
  );
}
