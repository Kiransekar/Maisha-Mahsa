// The connection-health strip (WS7.7 — UX research T4: feeds going stale SILENTLY is a strong
// finding across 5 angles, and the WS7 contract calls it "the single most dangerous gap").
//
// Shapes mirror api/app/core/freshness.py exactly (endpoint: GET /api/health/connections, wired in
// create_app()). Read that file before changing these — it is the authority on staleness, not this
// component. The prose on screen is the SERVER's headline plus the server's per-source note; this
// file adds no claim of its own about what any figure elsewhere is showing.
//
// Voice (research open question #8 — staleness must make the user trust the STALE NUMBER less
// without making them distrust the product): this strip is framed as the product WORKING. It is
// the age of the inputs, stated plainly. It never apologises and never implies breakage.

import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { ErrorState } from "./ErrorState";
import { useTraceId } from "../lib/trace";
import { effectiveState, type VerifyState } from "./VerifiedNumber";

export type SourceFreshness = {
  key: string;
  label: string;
  last_updated: string | null; // ISO date; null == never synced (never a fabricated date)
  age_days: number | null; // null == never synced (never 0)
  threshold_days: number;
  stale: boolean;
  synced: boolean;
  note: string;
};

export type FreshnessData = {
  as_of: string;
  sources: SourceFreshness[];
  overall: {
    status: "fresh" | "stale" | "unknown";
    healthy: boolean;
    headline: string;
    worst_age_days: number | null;
    never_synced: string[];
    stale: string[];
  };
};

/** Shared cache key so every screen asking "is source X stale?" costs one request, not N. */
export const FRESHNESS_QUERY_KEY = ["health", "connections"] as const;

export function useConnectionHealth() {
  return useQuery({
    queryKey: FRESHNESS_QUERY_KEY,
    queryFn: () => api<FreshnessData>("/health/connections"),
  });
}

/**
 * Three states, not two. "We checked and the inputs are old" and "we could not check" are
 * different facts, and wording the second as the first is a fabricated cause (invariant 3).
 *
 *   fresh    — the server checked this source and it is inside its threshold.
 *   stale    — the server checked it and it is past its threshold (never-synced arrives here too,
 *              because freshness.py sends stale=true for it; one rule, not two that can drift).
 *   unknown  — the freshness payload is missing (health call failed) or does not carry this key.
 */
export type SourceState = "fresh" | "stale" | "unknown";

export function sourceState(data: FreshnessData | undefined, key: string): SourceState {
  const source = data?.sources.find((s) => s.key === key);
  if (!source) return "unknown";
  return source.stale ? "stale" : "fresh";
}

/**
 * "Can a ✓ stand on this source?" — false for BOTH stale and unknown, deliberately.
 *
 * Failing closed is right for the badge: an unconfirmed ✓ is exactly the fabricated-verification
 * failure invariant 1 exists to prevent, and erring the other way would let one failed health
 * request silently restore ✓ across every screen. But a caller that WORDS the downgrade must ask
 * sourceState() instead — this boolean cannot tell the user why, and "unknown" is not "stale".
 */
export function isSourceStale(data: FreshnessData | undefined, key: string): boolean {
  return sourceState(data, key) !== "fresh";
}

/** The composition other screens want: a payload state, downgraded by real freshness. */
export function stateForSource(
  state: VerifyState,
  data: FreshnessData | undefined,
  key: string,
): VerifyState {
  return effectiveState(state, isSourceStale(data, key));
}

/**
 * Status word + hue for one source. Never-synced is its own state — it is neither healthy nor
 * hidden, because "no data at all" is a different fact from "old data".
 * ponytail: verification hues, not money hues — stale maps to the same ◐ a figure downgrades to.
 */
function status(s: SourceFreshness): { word: string; color: string } {
  if (!s.synced) return { word: "never synced", color: "var(--color-verify-unbacked)" };
  if (s.stale) return { word: "stale", color: "var(--color-verify-pending)" };
  return { word: "current", color: "var(--color-verify)" };
}

/** Age, in the user's terms. `null` days is never rendered as 0 — it is stated as unknown. */
function age(s: SourceFreshness): string {
  if (s.age_days === null) return "no data yet";
  if (s.age_days < 0) return `dated ${-s.age_days} day(s) in the future`;
  if (s.age_days === 0) return "today";
  return `${s.age_days} day(s) old`;
}

export function ConnectionHealth() {
  const { data, isLoading, error, refetch } = useConnectionHealth();
  const traceId = useTraceId("health");

  if (isLoading && !data)
    return <p style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>Checking data sources…</p>;

  // Anti-pattern #14: a failed freshness check never renders a blank strip — that would read as
  // "all clear". We say we could not check, and keep any last-known reading marked as such.
  if (error)
    return (
      <ErrorState error={error} traceId={traceId} onRetry={() => void refetch()}>
        {data && (
          <div style={{ marginTop: 12 }}>
            <Note>
              Last reading we managed to take, from {data.as_of}. It may itself be out of date —
              until this check succeeds, the current age of these sources is unknown.
            </Note>
            <Strip data={data} />
          </div>
        )}
      </ErrorState>
    );

  // The query settled with no payload. Rendering nothing here would read as a clean bill of health
  // — the silent-staleness failure this whole ticket exists to close. Say it is unknown instead,
  // and do not name a cause we cannot know (invariant 3).
  if (!data)
    return (
      <Panel>
        <Header />
        <Note>
          We could not determine how fresh your data sources are — this check came back with
          nothing. That is not a clean bill of health: the age of the inputs behind your figures is
          unknown right now, and unknown is not current.
        </Note>
        <button
          onClick={() => void refetch()}
          style={{
            marginTop: 10,
            background: "var(--color-accent)",
            color: "var(--color-on-accent)",
            border: "none",
            padding: "7px 14px",
            borderRadius: 4,
            fontSize: 13,
            cursor: "pointer",
            fontFamily: "inherit",
            fontWeight: 500,
          }}
        >
          Check again
        </button>
      </Panel>
    );

  return (
    <Panel>
      <Header asOf={data.as_of} />
      {/* The server's own headline, verbatim. It knows which sources breached; this component does
          not know what any other screen is currently rendering, so it claims nothing about it. */}
      <Note>{data.overall.headline}</Note>
      <Strip data={data} />
    </Panel>
  );
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <section
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)", // borders, not shadows (BRAND_THEME §3)
        borderRadius: 8,
        padding: "14px 16px",
      }}
    >
      {children}
    </section>
  );
}

function Header({ asOf }: { asOf?: string }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        alignItems: "baseline",
        justifyContent: "space-between",
        flexWrap: "wrap",
      }}
    >
      {/* fontWeight is explicit: hierarchy comes from size + tracking, never weight, and the
          browser default for an h2 is bold 700. */}
      <h2 style={{ fontSize: 14, fontWeight: 500, letterSpacing: "-0.01em", margin: 0 }}>
        Where your data comes from
      </h2>
      <span className="tnum" style={{ color: "var(--color-ink-faint)", fontSize: 11 }}>
        {asOf ? `checked ${asOf}` : "not checked"}
      </span>
    </div>
  );
}

function Strip({ data }: { data: FreshnessData }) {
  return (
    <div style={{ marginTop: 12, borderTop: "1px solid var(--color-border)" }}>
      {data.sources.map((s) => {
        const st = status(s);
        return (
          <div
            key={s.key}
            style={{
              display: "flex",
              gap: 12,
              alignItems: "baseline",
              flexWrap: "wrap",
              padding: "8px 0",
              borderBottom: "1px solid var(--color-border)",
              fontSize: 13,
            }}
          >
            <span style={{ flex: "1 1 160px" }}>{s.label}</span>
            <span className="tnum" style={{ color: "var(--color-ink-muted)", flex: "0 0 auto" }}>
              {s.last_updated ?? "—"}
            </span>
            <span
              className="tnum"
              style={{ color: "var(--color-ink-faint)", flex: "0 0 auto", fontSize: 12 }}
            >
              {age(s)}
            </span>
            <span style={{ color: st.color, fontSize: 12, flex: "0 0 auto" }}>{st.word}</span>
            {/* The server's own sentence, verbatim — it names the threshold it breached. */}
            <span style={{ flexBasis: "100%", color: "var(--color-ink-faint)", fontSize: 11 }}>
              {s.note}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <p style={{ margin: "6px 0 0", color: "var(--color-ink-muted)", fontSize: 12, lineHeight: 1.5 }}>
      {children}
    </p>
  );
}
