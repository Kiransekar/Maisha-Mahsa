import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";
import { ConnectionHealthStrip } from "./ConnectionHealth";
import { RulePackVersion } from "./RulePackVersion";

// Ordered by the roles in app/core/landing.py: Owner lands on Today, Accountant on the Exception
// Inbox, CA on the Audit Room. Stable ordering is part of the trust contract (UX research T2 —
// finance users punish unannounced relocation harder than any other UX failure), so nav entries
// get appended, never reshuffled.
const NAV = [
  { to: "/today", label: "Today" },
  { to: "/inbox", label: "Exception Inbox" },
  { to: "/approvals", label: "Approvals" },
  { to: "/domains", label: "Domains" },
  { to: "/audit", label: "Audit Room" },
  // T2: appended, never reshuffled.
  { to: "/file", label: "File returns" },
  { to: "/payroll-run", label: "Payroll run" },
  { to: "/ask", label: "Ask Maisha" },
  { to: "/statements", label: "Statements" },
  { to: "/settings", label: "Settings" },
  { to: "/cfo", label: "CFO strategy" },
];

// The app shell on the brand system (docs/BRAND_THEME.md): warm paper ground, hairline borders
// as the only elevation, brass reserved for the active/primary state. No shadows, no gradients.
export function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="shell">
      <aside className="shell-aside">
        <div style={{ letterSpacing: "-0.02em", marginBottom: 22, fontSize: 15 }}>
          Maisha<span style={{ color: "var(--color-ink-faint)" }}>·</span>Mahsa
        </div>
        <nav className="shell-nav">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              style={({ isActive }) => ({
                padding: "7px 10px",
                borderRadius: 4,
                fontSize: 13,
                textDecoration: "none",
                whiteSpace: "nowrap",
                color: isActive ? "var(--color-accent)" : "var(--color-ink-muted)",
                background: isActive ? "var(--color-accent-sunk)" : "transparent",
              })}
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div
          className="shell-footnote"
          style={{
            marginTop: 24,
            paddingTop: 14,
            borderTop: "1px solid var(--color-border)",
            color: "var(--color-ink-faint)",
            fontSize: 11,
            lineHeight: 1.5,
          }}
        >
          Every figure here is recomputed by a second engine before you see it. Figures that
          aren't say so.
          {/* WS10.4 — byte-exact disclaimer, mirror of app.core.legal.DISCLAIMER_TEXT
              (do not reword; Shell.test.tsx pins it). */}
          <div style={{ marginTop: 10 }}>
            software tool, not the practice of chartered accountancy; outputs require
            professional verification
          </div>
          {/* WS1.E3: rule-pack version, rendered only when Mahsa reports it. */}
          <RulePackVersion />
        </div>
      </aside>
      <main className="shell-main">
        {/* P1-6: visible on every screen once a source goes stale/broken, quiet otherwise —
            reuses the same hook Approvals wires, never a second staleness rule. */}
        <ConnectionHealthStrip />
        {children}
      </main>
    </div>
  );
}
