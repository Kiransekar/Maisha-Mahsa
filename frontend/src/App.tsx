import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Shell } from "./components/Shell";
import { Today } from "./routes/Today";
import { Inbox } from "./routes/Inbox";
import { Approvals } from "./routes/Approvals";
import { Domains } from "./routes/Domains";
import { Domain } from "./routes/Domain";
import { AuditRoom } from "./routes/AuditRoom";
import { Onboarding } from "./routes/Onboarding";
import { Filings } from "./routes/Filings";
import { PayrollRun } from "./routes/PayrollRun";
import { Statements } from "./routes/Statements";
import { Ask } from "./routes/Ask";
import { SignIn } from "./routes/SignIn";
import { Settings } from "./routes/Settings";
import { CaAccept } from "./routes/CaAccept";
import { Cfo } from "./routes/Cfo";
import {
  sessionStatus,
  switchOrganization,
  useActiveOrganization,
  useListOrganizations,
  useSession,
} from "./lib/auth";

/**
 * The route gate. Before this existed, `sessionStatus` had exactly ONE consumer in the whole
 * repo — SignIn.tsx — and it only bounced an ALREADY-authed visitor away. /today /inbox
 * /approvals /domains /d/:domain /audit /onboarding all rendered for anyone who typed the URL.
 *
 * Two things this must get right, and they pull in opposite directions:
 *  · A guest must never reach a financial figure. → "guest" redirects, it does not render.
 *  · A guest must never see a state that LOOKS like real data loading (WS7 anti-pattern #14 /
 *    T9: a skeleton where a ledger belongs reads as "my data is here, just slow"). So the
 *    indeterminate state is a plain sentence about the SESSION, with no figure, no skeleton and
 *    no chrome that implies an account behind it.
 *
 * `loading` is deliberately NOT treated as either one — see `sessionStatus`.
 */
function RequireAuth({ children }: { children: ReactNode }) {
  const session = useSession();
  const location = useLocation();
  const status = sessionStatus(session.data, session.isPending);

  if (status === "loading") {
    return (
      <p style={{ maxWidth: 380, margin: "10vh auto 0", color: "var(--color-ink-muted)", fontSize: 13 }}>
        Checking your session…
      </p>
    );
  }
  if (status === "guest") {
    // `from` so sign-in returns the user to what they actually asked for.
    return <Navigate to="/sign-in" replace state={{ from: location.pathname + location.search }} />;
  }
  return <>{children}</>;
}

/**
 * Org switcher. Native `<select>` on purpose (ladder rung 4) — this needs to be correct, not
 * bespoke. The correctness lives in `switchOrganization`, which clears BOTH the react-query cache
 * and the cached JWT; rendering it here is what stops that from being dead code.
 *
 * Hidden below two orgs: a picker with one option is noise, and T2 (unannounced layout churn)
 * says do not put chrome on screen that does nothing.
 */
function OrgSwitcher() {
  const queryClient = useQueryClient();
  const active = useActiveOrganization();
  const orgs = useListOrganizations();
  const list = orgs.data ?? [];
  if (list.length < 2) return null;

  return (
    <label
      style={{ display: "block", fontSize: 11, color: "var(--color-ink-faint)", marginBottom: 18 }}
    >
      Organisation
      <select
        value={active.data?.id ?? ""}
        onChange={(e) => {
          void switchOrganization(queryClient, active.data?.id, e.target.value);
        }}
        style={{
          display: "block",
          marginTop: 4,
          padding: "6px 10px",
          borderRadius: 4,
          border: "1px solid var(--color-border-strong)",
          background: "var(--color-surface)",
          color: "var(--color-ink)",
          fontSize: 13,
          fontFamily: "inherit",
        }}
      >
        {list.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function App() {
  return (
    <Routes>
      {/* The only route outside the gate. Rendered bare — no Shell, because the nav is an
          authenticated surface and a guest should not see the product's internal structure. */}
      <Route path="/sign-in" element={<SignIn />} />
      <Route
        path="*"
        element={
          <RequireAuth>
            <Shell>
              <OrgSwitcher />
              <Routes>
                {/* Owner's landing per app/core/landing.py ROLE_LANDING. */}
                <Route path="/" element={<Navigate to="/today" replace />} />
                <Route path="/today" element={<Today />} />
                <Route path="/inbox" element={<Inbox />} />
                <Route path="/approvals" element={<Approvals />} />
                <Route path="/domains" element={<Domains />} />
                <Route path="/d/:domain" element={<Domain />} />
                <Route path="/audit" element={<AuditRoom />} />
                <Route path="/onboarding" element={<Onboarding />} />
                {/* T2: appended, never reshuffled. */}
                <Route path="/file" element={<Filings />} />
                <Route path="/payroll-run" element={<PayrollRun />} />
                <Route path="/statements" element={<Statements />} />
                <Route path="/ask" element={<Ask />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/ca/accept" element={<CaAccept />} />
                <Route path="/cfo" element={<Cfo />} />
                <Route path="*" element={<p>Not found.</p>} />
              </Routes>
            </Shell>
          </RequireAuth>
        }
      />
    </Routes>
  );
}
