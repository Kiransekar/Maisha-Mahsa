// The 4-question error template — UX research T6 + anti-pattern #6 ("Something went wrong" was
// described by users as *taunting*). Every failure state answers, in this order:
//
//   1. What happened?              — in plain language, naming the actual thing that failed
//   2. Is my money / filing safe?  — the question users are actually asking. Answer it FIRST-class.
//   3. What do I do next?          — a concrete action, never "try again later"
//   4. Traceable ID                — so support can find this exact failure
//
// Anti-pattern #14 (blank screen reads as data loss): a failure never renders an empty shell.
// If we have last-known data we show it, marked stale, rather than nothing.

import { ApiError } from "../lib/api";

export type ErrorKind = "mahsa_down" | "api_down" | "unknown";

/** A read failed (nothing could have changed) vs a write failed (something may have). */
export type Operation = "read" | "write";

// Exported so the offline path can be pinned directly: a real offline fetch() rejects with a
// plain TypeError (not an ApiError — there was no HTTP response at all), and that must classify
// the same way a down server does, so the SAME copy + the SAME stale-marking machinery engage
// whether the network is unreachable or the server is. See ErrorState.test.ts.
export function classify(error: unknown): ErrorKind {
  if (error instanceof ApiError) return error.status >= 500 ? "api_down" : "unknown";
  return "api_down";
}

const READ_COPY: Record<ErrorKind, { what: string; safe: string; next: string }> = {
  mahsa_down: {
    what: "Mahsa, the engine that independently recomputes every figure, is unreachable.",
    safe: "Yes. Nothing was written and no filing was submitted. Figures below are simply not verified — which is why none of them show ✓.",
    next: "You can keep reading, but don't file from an unverified figure. Retry below; if it persists past a few minutes, send us the ID.",
  },
  api_down: {
    what: "We couldn't reach the Maisha server to load this view.",
    safe: "Yes. This was a read that failed — nothing was changed, submitted, or lost. Your data is on the server, not in this page.",
    next: "Retry below. If it keeps failing, your connection or our server is down — send us the ID and nothing will have been altered meanwhile.",
  },
  unknown: {
    what: "This view failed to load, and we don't yet have a precise reason.",
    safe: "Yes — this was a read, so nothing was changed or submitted. We are not going to guess at the cause.",
    next: "Retry below. If it repeats, send us the ID so we can trace this exact failure.",
  },
};

// A WRITE that failed must never claim "nothing was changed" — the server may have committed some,
// all, or none of it. Claiming safety we cannot verify is the same class of lie as a fabricated ✓.
// `committed` carries the server's own count when it reported one.
function writeCopy(kind: ErrorKind, committed?: number): { what: string; safe: string; next: string } {
  const partial = committed !== undefined && committed > 0;
  return {
    what:
      kind === "mahsa_down"
        ? "Mahsa became unreachable while this change was being written."
        : "The change you submitted did not complete.",
    safe: partial
      ? `Partly. ${committed} item(s) were already sealed to the audit chain before this failed — those stand and are visible in the audit trail. Anything beyond that did not go through. Nothing was filed with a statutory portal.`
      : "We can't confirm either way from here, so we won't claim it. Nothing was filed with a statutory portal. Check the audit trail below before retrying — a sealed entry means it went through.",
    next: partial
      ? "Don't blindly retry — re-select only what is still outstanding, or you may double-apply the sealed items. Send us the ID if the counts look wrong."
      : "Open the audit trail and confirm whether the change landed before retrying. If it isn't there, retry is safe. Send us the ID either way.",
  };
}

export function ErrorState({
  error,
  traceId,
  onRetry,
  operation = "read",
  committed,
  kind: kindOverride,
  children,
}: {
  error: unknown;
  traceId: string;
  onRetry?: () => void;
  /** "write" REQUIRED for any failed mutation — read copy asserts a safety we can't claim. */
  operation?: Operation;
  /** Rows the server reported as already committed before it failed, if it reported one. */
  committed?: number;
  kind?: ErrorKind;
  children?: React.ReactNode; // last-known data, if we have any (anti-pattern #14)
}) {
  const kind = kindOverride ?? classify(error);
  const c = operation === "write" ? writeCopy(kind, committed) : READ_COPY[kind];

  return (
    <div>
      <div
        style={{
          border: "1px solid var(--color-border-strong)",
          background: "var(--color-surface)",
          borderRadius: 8,
          padding: "16px 18px",
          fontSize: 13,
          lineHeight: 1.55,
        }}
      >
        <Q q="What happened">{c.what}</Q>
        <Q q="Is your money and filing safe">{c.safe}</Q>
        <Q q="What to do next">{c.next}</Q>
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 14 }}>
          {onRetry && (
            <button
              onClick={onRetry}
              style={{
                background: "var(--color-accent)",
                color: "var(--color-on-accent)",
                border: "none",
                padding: "7px 14px",
                borderRadius: 4,
                fontSize: 13,
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              Retry
            </button>
          )}
          <span className="ident" style={{ color: "var(--color-ink-faint)", fontSize: 11 }}>
            ref {traceId}
          </span>
        </div>
      </div>
      {children}
    </div>
  );
}

function Q({ q, children }: { q: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div
        style={{
          fontSize: 10,
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          color: "var(--color-ink-faint)",
        }}
      >
        {q}
      </div>
      <div>{children}</div>
    </div>
  );
}
