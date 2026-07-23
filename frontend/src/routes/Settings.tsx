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
import { api, ApiError } from "../lib/api";
import { ErrorState } from "../components/ErrorState";
import { useTraceId } from "../lib/trace";
import { Empty, H2, Header } from "./Today";

// ── types (server shapes from app/web/api_domains.py) ────────────────────────

export type PendingInvite = { membership_id: number; email: string; invited_at: string };
type PendingResponse = { invites: PendingInvite[] };
type InviteResponse = { membership_id: number; role: string; status: string; seat: string };

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
    </section>
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
