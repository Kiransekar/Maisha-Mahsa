// WS4.3 — the sign-in route. Email+password via the official Better Auth client (no hand-rolled
// auth call). A failed sign-in is a mutation attempt against the auth server, so it renders
// through the SAME 4-question ErrorState the rest of the product uses for a failed write
// (docs/WS7_BUILD_CONTRACT.md T6) — not a bespoke "invalid credentials" banner.
//
// SECOND FACTOR (MASTER_PLAN §WS4.3 "MFA enforced for Owner/Admin/Approver"). When the account
// has 2FA enabled, `signIn.email` does NOT return a session — it returns `{ twoFactorRedirect:
// true }` and the sign-in is incomplete until a TOTP code is verified (better-auth two-factor
// client plugin, node_modules/better-auth/dist/plugins/two-factor/client.mjs). This route now
// handles that second step instead of treating the redirect payload as success, which is what
// would otherwise happen: a truthy `data` navigating to /today with no session, landing the user
// straight back on the gate.
//
// ⚠️ TWO THINGS THE OWNER MUST DO — the SPA cannot do either, and neither is silently omitted:
//  1. Enable `twoFactor()` on the Better Auth server. Without it the /two-factor/* endpoints
//     404 and `twoFactorRedirect` never appears, so this branch is simply never taken.
//  2. Enforcement is the API's, not this form's: a client cannot enforce MFA on itself. The
//     server-side policy is app/core/principal.mfa_required + betterauth.assert_mfa_satisfied,
//     which is OPT-IN on MAISHA_BETTER_AUTH_MFA_CLAIM and OFF until the owner adds that claim to
//     the JWT payload. Until then §WS4.3's "enforced" is NOT satisfied end-to-end, and this
//     comment is the honest record of that rather than a checkbox.
//
// ENROLMENT (deferred, stated): turning 2FA ON for an account needs
// `authClient.twoFactor.enable({ password })` → `getTotpUri()` → QR → `verifyTotp` → backup
// codes. That belongs on an account-settings route, which does not exist in this SPA and is not
// among this ticket's owned files. Without it an Owner can complete a 2FA challenge but cannot
// self-enrol; enrolment must be done on the Better Auth side until that route is built.
//
// Social/OTP: the base client exposes `signIn.social(...)`, but with no endpoint telling this
// SPA which providers the owner has actually configured server-side, a hardcoded "Continue with
// Google" button risks pointing at a provider that isn't wired — a broken button is worse than
// no button (the same "never invent" principle §0.6 applies to UI affordances, not just ₹).
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { authClient, sessionStatus, useSession } from "../lib/auth";
import { ErrorState } from "../components/ErrorState";
import { useTraceId } from "../lib/trace";

const inputStyle: React.CSSProperties = {
  width: "100%",
  marginTop: 4,
  padding: "9px 12px",
  borderRadius: 4,
  border: "1px solid var(--color-border-strong)",
  background: "var(--color-surface)",
  color: "var(--color-ink)",
  fontSize: 14,
  fontWeight: 400,
};

const buttonStyle = (enabled: boolean): React.CSSProperties => ({
  width: "100%",
  background: "var(--color-accent)",
  color: "var(--color-on-accent)",
  border: "none",
  padding: "9px 16px",
  borderRadius: 4,
  fontSize: 13,
  fontWeight: 400,
  fontFamily: "inherit",
  cursor: enabled ? "pointer" : "not-allowed",
  opacity: enabled ? 1 : 0.5,
});

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: 12,
  color: "var(--color-ink-muted)",
  marginBottom: 16,
};

/**
 * Better Auth signals "credentials accepted, second factor still required" with a
 * `twoFactorRedirect` flag on the sign-in response instead of a session. Pure and exported so the
 * branch is directly testable — mistaking this payload for a completed sign-in is the exact bug
 * that would let a 2FA-protected account through the form and into a signed-out /today.
 */
export function needsSecondFactor(data: unknown): boolean {
  return Boolean((data as { twoFactorRedirect?: unknown } | null)?.twoFactorRedirect);
}

export function SignIn() {
  const session = useSession();
  const status = sessionStatus(session.data, session.isPending);
  const navigate = useNavigate();
  const location = useLocation();
  const traceId = useTraceId("sign-in");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [awaitingTotp, setAwaitingTotp] = useState(false);

  const dest = () => (location.state as { from?: string } | null)?.from ?? "/today";

  const signInMutation = useMutation({
    mutationFn: async (vars: { email: string; password: string }) => {
      const { data, error } = await authClient.signIn.email(vars);
      if (error) throw new Error(error.message ?? "Sign-in failed.");
      return data;
    },
    onSuccess: (data) => {
      // Not signed in yet — a second factor is outstanding. Do NOT navigate.
      if (needsSecondFactor(data)) {
        setAwaitingTotp(true);
        setPassword("");
        return;
      }
      navigate(dest(), { replace: true });
    },
  });

  const totpMutation = useMutation({
    mutationFn: async (vars: { code: string }) => {
      const { data, error } = await authClient.twoFactor.verifyTotp({ code: vars.code });
      if (error) throw new Error(error.message ?? "That code wasn't accepted.");
      return data;
    },
    onSuccess: () => navigate(dest(), { replace: true }),
  });

  // Already signed in — don't show the form (and never show it behind a loading flash that
  // could be mistaken for "you must sign in again").
  if (status === "authed") return <Navigate to={dest()} replace />;

  const canSubmit = email.trim() !== "" && password !== "" && !signInMutation.isPending;
  const canSubmitCode = code.trim().length >= 6 && !totpMutation.isPending;

  return (
    <section style={{ maxWidth: 380, margin: "10vh auto 0" }}>
      <h1 style={{ fontSize: 24, fontWeight: 400, letterSpacing: "-0.01em", marginBottom: 4 }}>
        {awaitingTotp ? "Two-factor code" : "Sign in"}
      </h1>
      <p style={{ color: "var(--color-ink-muted)", fontSize: 13, marginBottom: 24 }}>
        {awaitingTotp
          ? "Your password was accepted. Enter the 6-digit code from your authenticator app to finish signing in."
          : "Every figure you see after this is recomputed by Mahsa before it's shown — not just reviewed."}
      </p>

      {status === "loading" && (
        <p style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>Checking your session…</p>
      )}

      {awaitingTotp ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmitCode) totpMutation.mutate({ code: code.trim() });
          }}
        >
          <label style={labelStyle}>
            6-digit code
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              style={{ ...inputStyle, fontVariantNumeric: "tabular-nums", letterSpacing: "0.2em" }}
              aria-label="Two-factor code"
            />
          </label>

          {totpMutation.isError && (
            <div style={{ marginBottom: 16 }}>
              <ErrorState
                error={totpMutation.error}
                traceId={traceId}
                operation="write"
                onRetry={() => totpMutation.reset()}
              />
            </div>
          )}

          <button type="submit" disabled={!canSubmitCode} style={buttonStyle(canSubmitCode)}>
            {totpMutation.isPending ? "Verifying…" : "Verify code"}
          </button>
        </form>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) signInMutation.mutate({ email, password });
          }}
        >
          <label style={{ ...labelStyle, marginBottom: 12 }}>
            Email
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={inputStyle}
              aria-label="Email"
            />
          </label>
          <label style={labelStyle}>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={inputStyle}
              aria-label="Password"
            />
          </label>

          {signInMutation.isError && (
            <div style={{ marginBottom: 16 }}>
              <ErrorState
                error={signInMutation.error}
                traceId={traceId}
                operation="write"
                onRetry={() => signInMutation.reset()}
              />
            </div>
          )}

          <button type="submit" disabled={!canSubmit} style={buttonStyle(canSubmit)}>
            {signInMutation.isPending ? "Signing in…" : "Sign in"}
          </button>
        </form>
      )}
    </section>
  );
}
