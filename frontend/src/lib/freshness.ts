// "Can a ✓ on THIS screen still be believed?" — lifted out of Approvals.tsx (WS7.6) so every
// screen that renders a badged figure threads the SAME real freshness check instead of each
// re-deriving its own (P1-6: Today.tsx and Domain.tsx were relying on `mahsa_up`/request-error
// alone and never asked /api/health/connections on the happy path — a ✓ could sit on stale
// source data with nothing on screen saying so). Approvals.tsx re-exports these so its own
// tests, and PayrollRun.tsx/Filings.tsx which already imported this set from "./Approvals",
// keep working unchanged.
//
// Two independent ways a ✓ can stop being believable, and booksFreshness reports the stronger:
//   · the SOURCES behind the figures are stale or have never synced (server's own judgement,
//     from /api/health/connections — never re-derived here);
//   · this PAGE's own payload is old, because the tab was left open.

import { useEffect, useState } from "react";
import type { FreshnessData } from "../components/ConnectionHealth";
import type { Freshness } from "../components/VerifiedNumber";

/** How long a page's own payload may stand behind a ✓ before it is restating figures nobody
 *  has re-checked. */
export const PAYLOAD_MAX_AGE_MS = 120_000;

export type BooksFreshness = { stale: Freshness; why: string | null };

function labelsFor(health: FreshnessData, keys: string[]): string {
  return keys.map((k) => health.sources.find((s) => s.key === k)?.label ?? k).join(", ");
}

/**
 * A missing health payload answers `"unknown"`, not `true` — the check itself failed, so we do
 * not KNOW the inputs are stale, only that we could not confirm they are current. Stating that as
 * "stale" would be inventing a cause we cannot know (invariant 3); the honest fact is "we could
 * not check". Both fail closed the same way (`effectiveState`/VerifiedNumber downgrade a ✓ on
 * `stale !== false`, "unknown" included) — only the WORDING differs, matching the distinction
 * `sourceState()`/`isSourceStale()` already draw one layer down. One failed health request must
 * never silently restore ✓ on a screen full of figures, and must never be MISreported as staleness.
 */
export function booksFreshness(
  health: FreshnessData | undefined,
  payloadAgeMs: number,
): BooksFreshness {
  if (health === undefined) {
    return {
      stale: "unknown",
      why: "We could not check when the sources behind these figures last synced, so nothing here is shown as ✓.",
    };
  }
  const never = health.overall.never_synced;
  if (never.length > 0) {
    return {
      stale: true,
      why: `${labelsFor(health, never)} has never synced, so the figures behind it are not fully backed.`,
    };
  }
  const stale = health.overall.stale;
  if (stale.length > 0) {
    return {
      stale: true,
      why: `${labelsFor(health, stale)} is past its freshness limit, so a recomputation against it no longer stands.`,
    };
  }
  if (payloadAgeMs > PAYLOAD_MAX_AGE_MS) {
    return {
      stale: true,
      why: `This was loaded ${ago(payloadAgeMs)} and has not been re-checked since. Reload for a ✓ you can rely on.`,
    };
  }
  return { stale: false, why: null };
}

/** Plain-language age. Never "0 minutes" — that reads as "just now" when it is up to 59s stale. */
export function ago(ms: number): string {
  const m = Math.floor(ms / 60_000);
  if (m < 1) return "less than a minute ago";
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`;
  const h = Math.floor(m / 60);
  return `${h} hour${h === 1 ? "" : "s"} ago`;
}

/** Re-render on a timer so a tab left open actually crosses the staleness threshold. Without
 *  this the downgrade would only fire on the next user interaction — i.e. never, in the case we
 *  care about. ponytail: a 30s tick, not a scheduled timeout; the resolution is plenty for a
 *  2-minute limit. */
export function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}
