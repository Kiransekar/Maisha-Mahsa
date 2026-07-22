// Owner's landing (WS7.3), rebuilt in React on the brand system. Reads /api/today, which is the
// SAME assembler the HTMX page renders — the two surfaces cannot show different numbers.
//
// Honesty rules carried from the server (never re-decided here):
//   · a figure's ✓/◐ state comes from the payload, never from the component
//   · a ₹-consequence the backend marked unknown renders "—", never ₹0
//   · Mahsa down => an explicit banner, not a silently thinner page

import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { inr } from "../lib/money";
import { VerifiedNumber, type VerifyState, type Working } from "../components/VerifiedNumber";
import { ErrorState } from "../components/ErrorState";

type Panel = Working & { label: string; value: string; state: VerifyState; note: string | null };
type NeedsYou = {
  domain: string;
  title: string;
  what: string;
  consequence: string;
  consequence_pending: boolean;
  action_label: string;
  action_href: string;
};
type Trouble = {
  what: string;
  domain: string;
  when: string;
  overdue: boolean;
  consequence_paise: number | null;
  consequence_kind: string;
  action_label: string;
  action_href: string;
};
type TodayData = {
  as_of: string;
  mahsa_up: boolean;
  cash_strip: Panel[];
  needs_you: NeedsYou[];
  trouble: Trouble[];
  penalties_avoided: { amount: string; estimate: boolean; basis: string; component_count: number };
};

// How the ₹-consequence was arrived at — stated, never implied (research: name the mechanism).
const KIND_NOTE: Record<string, string> = {
  recorded: "recorded penalty",
  accruing: "accruing now",
  if_missed: "if missed",
  pending: "amount not yet known",
};

export function Today() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["today"],
    queryFn: () => api<TodayData>("/today"),
  });

  if (isLoading && !data) return <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>;

  // Anti-pattern #14: never a blank shell on failure. If react-query still holds the last
  // successful payload we render it below the error, explicitly marked stale (T4) — a figure
  // on stale inputs is downgraded from ✓, never shown as still-verified.
  if (error) {
    return (
      <div>
        <Header title="Today" as_of={data?.as_of} />
        <ErrorState error={error} traceId={`today-${Date.now().toString(36)}`} onRetry={refetch}>
          {data && (
            <>
              <H2>Last known — not current</H2>
              <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                {data.cash_strip.map((p) => (
                  <VerifiedNumber
                    key={p.label}
                    label={p.label}
                    value={p.value}
                    state={p.state}
                    note={p.note}
                    working={p}
                    asOf={data.as_of}
                    stale
                  />
                ))}
              </div>
            </>
          )}
        </ErrorState>
      </div>
    );
  }
  if (!data) return null;

  return (
    <section>
      <Header title="Today" as_of={data.as_of} />
      {!data.mahsa_up && <MahsaDownBanner />}

      <H2>Cash</H2>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        {data.cash_strip.map((p) => (
          <VerifiedNumber
            key={p.label}
            label={p.label}
            value={p.value}
            state={p.state}
            note={p.note}
            working={p}
            asOf={data.as_of}
          />
        ))}
      </div>

      <H2>Needs you</H2>
      {data.needs_you.length === 0 ? (
        <Empty>Nothing waiting on your sign-off.</Empty>
      ) : (
        data.needs_you.map((n) => (
          <Row key={n.domain} href={n.action_href} action={n.action_label}>
            <strong>{n.title}</strong>
            <div style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>{n.what}</div>
            <div style={{ color: "var(--color-ink-faint)", fontSize: 12 }}>{n.consequence}</div>
          </Row>
        ))
      )}

      <H2>Trouble radar</H2>
      {data.trouble.length === 0 ? (
        <Empty>No deadlines or risks in view.</Empty>
      ) : (
        data.trouble.map((t, i) => (
          <Row key={`${t.domain}-${i}`} href={t.action_href} action={t.action_label}>
            <strong style={{ color: t.overdue ? "var(--color-money-out)" : undefined }}>
              {t.what}
            </strong>
            <div style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>{t.when}</div>
            <div className="tnum" style={{ fontSize: 13, marginTop: 2 }}>
              {t.consequence_paise === null ? (
                <span style={{ color: "var(--color-ink-faint)" }}>
                  ₹ impact not yet known — we don't guess
                </span>
              ) : (
                <>
                  {inr(t.consequence_paise)}{" "}
                  <span style={{ color: "var(--color-ink-faint)", fontSize: 12 }}>
                    {KIND_NOTE[t.consequence_kind] ?? t.consequence_kind}
                  </span>
                </>
              )}
            </div>
          </Row>
        ))
      )}

      <div
        style={{
          marginTop: 28,
          padding: "12px 16px",
          background: "var(--color-surface-sunk)",
          border: "1px solid var(--color-border)",
          borderRadius: 8,
        }}
      >
        <span className="tnum" style={{ fontSize: 18 }}>
          {data.penalties_avoided.amount}
        </span>{" "}
        <span style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>
          penalties avoided{data.penalties_avoided.estimate ? " (estimate)" : ""}
        </span>
        <div style={{ color: "var(--color-ink-faint)", fontSize: 12, marginTop: 4 }}>
          {data.penalties_avoided.basis}
        </div>
      </div>
    </section>
  );
}

// ── shared bits ──────────────────────────────────────────────────────────────
export function Header({ title, as_of }: { title: string; as_of?: string }) {
  return (
    <div style={{ marginBottom: 22 }}>
      <h1 style={{ fontSize: 26, letterSpacing: "-0.02em", margin: 0, fontWeight: 500 }}>{title}</h1>
      {as_of && (
        <div className="tnum" style={{ color: "var(--color-ink-faint)", fontSize: 12 }}>
          as of {as_of}
        </div>
      )}
    </div>
  );
}

export function H2({ children }: { children: React.ReactNode }) {
  return (
    <h2
      style={{
        fontSize: 12,
        textTransform: "uppercase",
        letterSpacing: "0.08em",
        color: "var(--color-ink-muted)",
        fontWeight: 500,
        margin: "28px 0 10px",
      }}
    >
      {children}
    </h2>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p
      style={{
        color: "var(--color-ink-faint)",
        fontSize: 13,
        border: "1px dashed var(--color-border)",
        borderRadius: 8,
        padding: "14px 16px",
        margin: 0,
      }}
    >
      {children}
    </p>
  );
}

function Row({
  children,
  href,
  action,
}: {
  children: React.ReactNode;
  href: string;
  action: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 16,
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: 8,
        padding: "12px 16px",
        marginBottom: 8,
      }}
    >
      <div>{children}</div>
      <a
        href={href}
        style={{
          background: "var(--color-accent)",
          color: "#fff",
          padding: "7px 14px",
          borderRadius: 4,
          fontSize: 13,
          textDecoration: "none",
          whiteSpace: "nowrap",
        }}
      >
        {action}
      </a>
    </div>
  );
}

export function MahsaDownBanner() {
  return (
    <div
      style={{
        border: "1px solid var(--color-verify-unbacked)",
        background: "var(--color-surface)",
        borderRadius: 8,
        padding: "12px 16px",
        marginBottom: 18,
        fontSize: 13,
      }}
    >
      <strong>Mahsa is unreachable.</strong> Nothing below has been independently recomputed, so
      no figure is shown as verified. This is the honest state — not a degraded one.
    </div>
  );
}

