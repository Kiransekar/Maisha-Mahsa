// P1-3 — the CA's own accept screen, /ca/accept.
//
// The invited CA signs in as themselves (RequireAuth in App.tsx already gates this route) and
// presses Accept. POST /api/ca/accept (app/core/ca_seat.accept_ca) matches the pending
// membership on the caller's OWN verified token — email + org from the JWT, never a URL token
// (§0.8: identity is the authorization here, by the backend's own design — see WS8.3 in
// PROGRESS.md). There is nothing for this screen to read out of the URL and pass along; a
// query-string invite token would be decorative at best and forgeable at worst.
//
// On success it lands on the CA role landing, the Audit Room (app/core/landing.ROLE_LANDING —
// Role.CA -> "audit_room" -> /audit).
// A 404 ("no pending CA invite for this account in this org") is an honest, expected outcome —
// not a system failure — so it gets its own plain sentence rather than the ErrorState template
// built for genuine breakage. Any other failure still goes through ErrorState (operation="write":
// a 4xx/5xx here means the accept did not go through, never claim otherwise).

import { useMutation } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { ErrorState } from "../components/ErrorState";
import { useTraceId } from "../lib/trace";
import { Header } from "./Today";

type AcceptResponse = { membership_id: number; status: string; referred_org: boolean };

/** True only for the honest "nothing to accept" case — everything else is a real failure. */
export function isNoPendingInvite(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

export function CaAcceptCard({
  onAccept,
  pending,
  error,
  success,
  traceId,
}: {
  onAccept: () => void;
  pending: boolean;
  error: unknown;
  success: boolean;
  traceId: string;
}) {
  if (success) {
    return (
      <section style={{ maxWidth: 480 }}>
        <Header title="Accept your CA seat" />
        <p style={{ fontSize: 13, color: "var(--color-ink-muted)" }}>
          Seat active — taking you to the Audit Room…
        </p>
      </section>
    );
  }

  return (
    <section style={{ maxWidth: 480 }}>
      <Header title="Accept your CA seat" />
      <p style={{ fontSize: 13, color: "var(--color-ink-muted)", lineHeight: 1.55, margin: "0 0 16px" }}>
        This seat is <strong style={{ fontWeight: 600, color: "var(--color-ink)" }}>free and
        unlimited</strong> — accepting adds you to the Audit Room for this organisation and never
        counts against anyone's plan.
      </p>

      {error && isNoPendingInvite(error) ? (
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
          No pending CA invite was found for your signed-in account in this organisation. Ask the
          firm to invite this exact email address, or switch to the organisation that invited you.
        </p>
      ) : error ? (
        <ErrorState error={error} traceId={traceId} operation="write" />
      ) : null}

      <button
        type="button"
        onClick={onAccept}
        disabled={pending}
        style={{
          background: pending ? "var(--color-surface-sunk)" : "var(--color-accent)",
          color: pending ? "var(--color-ink-muted)" : "var(--color-on-accent)",
          border: "none",
          padding: "9px 18px",
          borderRadius: 4,
          fontSize: 13,
          fontFamily: "inherit",
          cursor: pending ? "not-allowed" : "pointer",
        }}
      >
        {pending ? "Accepting…" : "Accept CA seat"}
      </button>
    </section>
  );
}

export function CaAccept() {
  const traceId = useTraceId("ca-accept");
  const accept = useMutation({
    mutationFn: () => api<AcceptResponse>("/ca/accept", { method: "POST", body: JSON.stringify({}) }),
  });

  // The actual redirect lives here, not in CaAcceptCard: `Navigate` needs a Router context, and
  // keeping the presentational card router-free is what lets it render via renderToStaticMarkup
  // in CaAccept.test.tsx without a <MemoryRouter> wrapper.
  if (accept.isSuccess) return <Navigate to="/audit" replace />;

  return (
    <CaAcceptCard
      onAccept={() => accept.mutate()}
      pending={accept.isPending}
      error={accept.error}
      success={false}
      traceId={traceId}
    />
  );
}
