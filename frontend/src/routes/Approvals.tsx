// WS7.6 — the approval screen. The one place in the product where a human commits real money,
// so it is the most trust-critical surface we ship.
//
// What this screen is FOR (docs/WS7_BUILD_CONTRACT.md + WS7_UX_RESEARCH.md):
//   · Restate, at the moment of approval, the figures actually being signed off — each with the
//     verification state Mahsa produced on THIS fold, not a cached badge from a list page.
//   · A figure Mahsa did not recompute is visibly distinct from one it did, and the screen says
//     so in words. Approving it is permitted; dressing it up as verified is not.
//   · The commit is typed-confirm, never a bare button (open question #4: the friction must read
//     as safety, not bureaucracy — so the confirm box sits directly under the restated total and
//     names what is about to be written).
//   · Success renders a persistent audit receipt (chain hash + timestamp), never a toast. A
//     disappearing confirmation is indistinguishable from nothing having happened.
//
// Verification state is NEVER decided here — every chip comes from the server's per-figure
// `state`, and an unrecognised state falls through VerifyChip to ✕, never ✓.
//
// THREE CORRECTIONS made after adversarial review — do not regress them:
//
//   1. WHAT THE COMMIT ACTUALLY BINDS TO. This screen used to say the entry was sealed against
//      `state_hash` — "the exact books shown above". That was false. The client never sends
//      state_hash; api/app/core/approvals.py :: record_decision re-folds the domain and
//      recomputes state_hash from the CURRENT books at click time. So the copy now states the
//      real binding (the fold taken at the moment of the click), and — because the decide
//      response returns the hash actually sealed — the receipt COMPARES it against the hash that
//      was on screen and says plainly if the books moved. A claim we can verify, not a promise.
//
//   2. SUB-RUPEE DRIFT IS THE PRODUCT. `inr()` is Math.round(paise/100), so a 40-paise GST/TDS
//      mismatch printed "differs by 0" and 12345678 vs 12345638 rendered identically. Drift is
//      now rendered in exact paise via `exactInr`, and when the two rounded figures collide the
//      exact pair is printed too. See `drift()` — a real mismatch must never read as agreement.
//
//   3. FRESHNESS IS ENFORCED, NOT ASSUMED. Chips used to render the raw server state forever, so
//      a tab left open showed ✓ on hours-old figures. Chips now go through `effectiveState` fed
//      by `booksFreshness()`, which combines the real /api/health/connections payload with the
//      age of this page's own data; the query also refetches on window focus.

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../lib/api";
import { inr, inrOrPending } from "../lib/money";
import { effectiveState, VerifyChip, type VerifyState } from "../components/VerifiedNumber";
import { useConnectionHealth, type FreshnessData } from "../components/ConnectionHealth";
import { ErrorState } from "../components/ErrorState";
import { useTraceId } from "../lib/trace";
import { Empty, H2, Header, MahsaDownBanner } from "./Today";

export type Figure = {
  target: string;
  label: string;
  claimed_paise: number;
  recomputed_paise: number | null;
  recomputed_values: Record<string, unknown> | null;
  state: string;
  note: string | null;
};

export type ApprovalItem = {
  domain: string;
  status: string;
  color: string;
  score: number | null;
  citations: { rule_id: string; text: string; citation: string }[];
  state_hash: string;
  resolution: string | null;
  figures: Figure[];
  figures_note: string | null;
  verified_total_paise: number | null;
  verified_count: number;
  unverified_count: number;
  all_verified: boolean;
  verdict_hash: string | null;
  rule_pack_version: string | null;
};

type ApprovalsData = {
  mahsa_up: boolean;
  as_of: string;
  items: ApprovalItem[];
  message?: string;
};

type Receipt = {
  domain: string;
  decision: string;
  audit_hash: string;
  state_hash: string; // the hash the server ACTUALLY sealed (its own re-fold)
  timestamp: string;
  user_id: string;
  /** The hash this screen had displayed when the button was pressed. Client-side, so the two can
   *  be compared: equal means the books did not move under the user, different means they did. */
  shown_state_hash?: string;
};

// ── pure logic (tested in Approvals.test.ts) ─────────────────────────────────

/** The typed-confirm gate. Mirrors the server rule exactly (`confirm_text.strip().lower()` vs
 *  the domain) so the button never enables on a phrase the API will reject — friction that
 *  produces a mystery 400 reads as bureaucracy, which is the failure mode research #4 names. */
export function confirmOk(typed: string, domain: string): boolean {
  return typed.trim().toLowerCase() === domain.trim().toLowerCase();
}

export type Stance = { tone: VerifyState; headline: string };

/** What a human is really being asked to sign, derived from the PER-FIGURE states rather than
 *  the server's roll-up counters — a roll-up can only ever be as honest as its worst figure, and
 *  deriving here makes it structurally impossible to print "all verified" over a ✕ row. */
export function approvalStance(figures: Figure[]): Stance {
  const bad = figures.filter((f) => f.state === "unbacked").length;
  const verified = figures.filter((f) => f.state === "verified").length;

  if (bad > 0) {
    return {
      tone: "unbacked",
      headline: `${bad} figure${bad === 1 ? "" : "s"} here ${bad === 1 ? "was" : "were"} recomputed by Mahsa and did NOT match. Approving signs off on a number Mahsa contradicts — correct it instead.`,
    };
  }
  if (figures.length === 0) {
    return {
      tone: "honest_pending",
      headline:
        "Nothing in this domain was recomputed. The verdict is real; the arithmetic behind it is not sealed.",
    };
  }
  if (verified < figures.length) {
    const n = figures.length - verified;
    return {
      tone: "honest_pending",
      headline: `${n} of ${figures.length} figures ${n === 1 ? "is" : "are"} not backed by a recomputation. You may still approve — it will be recorded as an unverified approval.`,
    };
  }
  return {
    tone: "verified",
    headline: `All ${figures.length} figures were independently recomputed by Mahsa and matched to the paisa.`,
  };
}

// ── exact money (CARDINAL 2) ─────────────────────────────────────────────────

// Grouping only. `inr()` in lib/money.ts deliberately rounds to the whole rupee for display, which
// is right for a headline total and catastrophic for a mismatch: a 40-paise drift is exactly the
// GST/TDS error this product exists to catch, and rounding prints it as agreement.
const GROUP = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** Exact money — rupees AND paise, never rounded. ₹1,23,456.78. */
export function exactInr(paise: number): string {
  const abs = Math.abs(Math.round(paise));
  return `${paise < 0 ? "-" : ""}₹${GROUP.format(Math.floor(abs / 100))}.${String(abs % 100).padStart(2, "0")}`;
}

export type Drift = {
  diffPaise: number;
  /** True when claimed and recomputed render to the SAME rupee string. Then the rounded figures
   *  alone would read as agreement, and the exact pair must be shown alongside the difference. */
  indistinguishable: boolean;
};

/** The claimed-vs-recomputed gap, in paise. `null` means there is genuinely nothing to report:
 *  either Mahsa produced no number, or it produced the identical one. Any other case — including
 *  a single paisa — is a real mismatch and returns a Drift. */
export function drift(claimedPaise: number, recomputedPaise: number | null): Drift | null {
  if (recomputedPaise === null || recomputedPaise === claimedPaise) return null;
  return {
    diffPaise: Math.abs(recomputedPaise - claimedPaise),
    indistinguishable: inr(claimedPaise) === inr(recomputedPaise),
  };
}

// ── freshness (HIGH) ─────────────────────────────────────────────────────────

/** How long this page's own payload may stand behind a ✓. An approval screen left open past this
 *  is restating figures nobody has re-checked, so the chips downgrade until it refetches. */
export const PAYLOAD_MAX_AGE_MS = 120_000;

export type BooksFreshness = { stale: boolean; why: string | null };

/** Plain-language age. Never "0 minutes" — that reads as "just now" when it is up to 59s stale. */
export function ago(ms: number): string {
  const m = Math.floor(ms / 60_000);
  if (m < 1) return "less than a minute ago";
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`;
  const h = Math.floor(m / 60);
  return `${h} hour${h === 1 ? "" : "s"} ago`;
}

function labelsFor(health: FreshnessData, keys: string[]): string {
  return keys.map((k) => health.sources.find((s) => s.key === k)?.label ?? k).join(", ");
}

/**
 * Can a ✓ on THIS screen still be believed?
 *
 * Two independent ways it can stop being believable, and we report the stronger one:
 *   · the SOURCES behind the books are stale or have never synced (server's own judgement, from
 *     /api/health/connections — we never re-derive staleness here);
 *   · this PAGE's payload is old, because the tab was left open.
 *
 * A missing health payload answers `stale`, deliberately and in line with isSourceStale(): if the
 * check did not come back we cannot confirm the inputs are current, and an unconfirmed ✓ is the
 * fabricated-verification failure invariant 1 exists to prevent. One failed health request must
 * never silently restore ✓ on the screen where money gets committed.
 *
 * ponytail: this is a WHOLE-SCREEN downgrade, not per-figure. The approvals payload carries no
 * per-figure source key, so any domain→source mapping would be a client-side guess — precisely the
 * invented binding correction #1 above exists to remove. Over-cautious is a safe direction; making
 * up which feed backs which figure is not. Upgrade path: have the server put the source keys it
 * actually folded onto each Figure, then downgrade per figure via stateForSource().
 */
export function booksFreshness(
  health: FreshnessData | undefined,
  payloadAgeMs: number,
): BooksFreshness {
  if (health === undefined) {
    return {
      stale: true,
      why: "We could not check when the sources behind these figures last synced, so nothing here is shown as ✓. You can still approve — it will be recorded as an unverified approval.",
    };
  }
  const never = health.overall.never_synced;
  if (never.length > 0) {
    return {
      stale: true,
      why: `${labelsFor(health, never)} has never synced, so the books behind these figures are not fully backed.`,
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
      why: `These figures were loaded ${ago(payloadAgeMs)} and have not been re-checked since. Reload before approving if you want a ✓ you can rely on.`,
    };
  }
  return { stale: false, why: null };
}

// ── screen ───────────────────────────────────────────────────────────────────

/** Re-render on a timer so a tab left open actually crosses the staleness threshold. Without this
 *  the downgrade would only fire on the next user interaction — i.e. never, in the case we care
 *  about. ponytail: a 30s tick, not a scheduled timeout; the resolution is plenty for a 2m limit. */
function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return now;
}

export function Approvals() {
  const qc = useQueryClient();
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const traceId = useTraceId("approvals");
  const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["approvals"],
    queryFn: () => api<ApprovalsData>("/approvals"),
    // Trust-critical: never serve this from cache without re-asking, and re-ask the moment the
    // user comes back to the tab. The global 30s staleTime is fine for reading, not for signing.
    staleTime: 0,
    refetchOnWindowFocus: true,
  });
  const health = useConnectionHealth();
  const now = useNow();

  const age = dataUpdatedAt ? now - dataUpdatedAt : 0;
  const fresh = booksFreshness(health.data, age);

  if (isLoading && !data) return <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>;

  if (error) {
    return (
      <div>
        <Header title="Approvals" as_of={data?.as_of} />
        {/* DELIBERATE, AND REVIEW-ACCEPTED — do not "fix" this by adding last-known figures.
            Every other screen falls back to stale data on error (anti-pattern #14, blank screens
            read as data loss). This one must not: a stale restatement rendered next to a live
            Approve button invites signing off figures nobody re-checked, which is the exact hazard
            this screen exists to prevent. A blank restatement here is the SAFER failure. */}
        <ErrorState error={error} traceId={traceId} onRetry={refetch}>
          <p style={{ color: "var(--color-ink-muted)", fontSize: 13, marginTop: 14 }}>
            No approval can be recorded while this view is failing. Nothing has been written, and we
            are deliberately not showing the last figures we had — approving against a stale
            restatement is the one mistake this screen is built to make impossible.
          </p>
        </ErrorState>
        <Receipts receipts={receipts} />
      </div>
    );
  }
  if (!data) return null;

  return (
    <section>
      <Header title="Approvals" as_of={data.as_of} />

      {/* The age of what you are reading, always stated — not only once it goes stale. */}
      <p style={{ color: "var(--color-ink-faint)", fontSize: 12, margin: "0 0 12px" }}>
        Figures below were read <span className="tnum">{ago(age)}</span>
        {fresh.stale ? " · not currently backed by a ✓" : " · current"}
      </p>

      {fresh.why && (
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
          {fresh.why}
        </p>
      )}

      {/* Invariant 6: Mahsa down is stated, never absorbed into a thinner page. */}
      {!data.mahsa_up && (
        <>
          <MahsaDownBanner />
          <p style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>
            {data.message ??
              "No approval is listed and none can be recorded until the gate is back."}
          </p>
        </>
      )}

      <Receipts receipts={receipts} />

      {data.mahsa_up &&
        (data.items.length === 0 ? (
          <>
            <H2>Waiting on you</H2>
            <Empty>Nothing is waiting on your sign-off.</Empty>
          </>
        ) : (
          <>
            <H2>Waiting on you · {data.items.length}</H2>
            {data.items.map((item) => (
              <ApprovalCard
                key={item.domain}
                item={item}
                stale={fresh.stale}
                ageMs={age}
                onDecided={(r) => {
                  setReceipts((prev) => [r, ...prev]);
                  qc.invalidateQueries({ queryKey: ["approvals"] });
                }}
              />
            ))}
          </>
        ))}
    </section>
  );
}

function ApprovalCard({
  item,
  stale,
  ageMs,
  onDecided,
}: {
  item: ApprovalItem;
  stale: boolean;
  ageMs: number;
  onDecided: (r: Receipt) => void;
}) {
  const [typed, setTyped] = useState("");
  const stance = approvalStance(item.figures);
  const shownTone = effectiveState(stance.tone, stale);
  const ready = confirmOk(typed, item.domain);

  const decide = useMutation({
    mutationFn: (decision: "approved" | "rejected") =>
      api<{ message: string; receipt: Receipt }>(`/approvals/${item.domain}/decide`, {
        method: "POST",
        body: JSON.stringify({ decision, confirm_text: typed }),
      }),
    onSuccess: (res) => {
      setTyped("");
      // Carry the hash we DISPLAYED alongside the one the server sealed, so the receipt can state
      // whether they are the same books rather than assuming it. See correction #1 at the top.
      onDecided({ ...res.receipt, shown_state_hash: item.state_hash });
    },
  });

  return (
    <div
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: 8,
        padding: "16px 18px",
        marginBottom: 12,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <strong style={{ fontSize: 16, fontWeight: 600, letterSpacing: "-0.01em" }}>
            {item.domain}
          </strong>
          <div style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>
            Mahsa verdict: {item.status}
            {item.score !== null && <span className="tnum"> · score {item.score}</span>}
          </div>
        </div>
        <VerifyChip state={shownTone} />
      </div>

      <p
        style={{
          fontSize: 13,
          fontWeight: 400,
          lineHeight: 1.55,
          margin: "12px 0 0",
          padding: "10px 12px",
          borderRadius: 4,
          border: `1px solid ${TONE_BORDER[shownTone]}`,
          background: "var(--color-surface-sunk)",
        }}
      >
        {stance.headline}
      </p>

      {/* T4: a silent downgrade is its own trust failure — say it was downgraded and why. */}
      {stale && stance.tone === "verified" && (
        <p style={{ color: "var(--color-verify-pending)", fontSize: 12, margin: "6px 0 0" }}>
          Downgraded from ✓ for now: Mahsa did recompute these, but we cannot confirm the inputs
          behind them are current, so the recomputation no longer stands on its own.
        </p>
      )}

      {/* The restatement. Claimed vs recomputed side by side — the whole basis of the signature. */}
      <H2>What you are approving</H2>
      {item.figures.length === 0 ? (
        <Empty>{item.figures_note ?? "No recomputable figure in this domain."}</Empty>
      ) : (
        item.figures.map((f) => <FigureRow key={f.target} figure={f} stale={stale} />)
      )}

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          flexWrap: "wrap",
          gap: 16,
          marginTop: 12,
          paddingTop: 12,
          borderTop: "1px solid var(--color-border)",
        }}
      >
        <span style={{ color: "var(--color-ink-muted)", fontSize: 13 }}>
          Verified total (recomputed figures only)
        </span>
        {/* Invariant 2: nothing verified means there is no total — never ₹0. */}
        {item.verified_total_paise === null ? (
          <span style={{ color: "var(--color-ink-faint)", fontSize: 13 }}>
            no verified figure — we don't guess a total
          </span>
        ) : (
          <span
            className="tnum"
            style={{ fontSize: 20, fontWeight: 400, letterSpacing: "-0.02em" }}
            title={exactInr(item.verified_total_paise)}
          >
            {inr(item.verified_total_paise)}
          </span>
        )}
      </div>

      {(item.verdict_hash || item.rule_pack_version) && (
        <div style={{ fontSize: 11, color: "var(--color-ink-faint)", marginTop: 6 }}>
          {item.verdict_hash ? (
            <>
              sealed <span className="ident">{item.verdict_hash}</span>
            </>
          ) : (
            "not sealed — no figure verified"
          )}
          {item.rule_pack_version && <> · rules {item.rule_pack_version}</>}
        </div>
      )}

      {item.citations.length > 0 && (
        <details style={{ marginTop: 10 }}>
          <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--color-ink-muted)" }}>
            Why this needs approval · {item.citations.length} rule
            {item.citations.length === 1 ? "" : "s"}
          </summary>
          <div style={{ fontSize: 12, color: "var(--color-ink-muted)", marginTop: 6 }}>
            {item.citations.map((c) => (
              <div key={c.rule_id} style={{ marginBottom: 4 }}>
                <span className="ident">{c.rule_id}</span> — {c.text}{" "}
                <span style={{ color: "var(--color-ink-faint)" }}>({c.citation})</span>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* The commit. Typed confirm, and the sentence above it names exactly what gets written —
          including the part we do NOT control. See correction #1 at the top of this file. */}
      <div
        style={{
          marginTop: 14,
          paddingTop: 14,
          borderTop: "1px solid var(--color-border)",
        }}
      >
        <label
          htmlFor={`confirm-${item.domain}`}
          style={{
            fontSize: 13,
            fontWeight: 400,
            lineHeight: 1.55,
            color: "var(--color-ink-muted)",
            display: "block",
          }}
        >
          This writes a permanent, hash-chained entry to the audit log. It is sealed against a fresh
          fold of the books taken <strong style={{ fontWeight: 600 }}>at the moment you click</strong>
          , not against the snapshot on this page — the server re-reads and re-hashes then. What you
          are reading was <span className="tnum">{ago(ageMs)}</span>, at books{" "}
          <span className="ident">{item.state_hash.slice(0, 16)}</span>. If they have moved since,
          the receipt will show a different hash and will say so. To confirm you have read the
          figures, type <strong className="ident">{item.domain}</strong>.
        </label>
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <input
            id={`confirm-${item.domain}`}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={item.domain}
            autoComplete="off"
            style={{
              border: "1px solid var(--color-border-strong)",
              background: "var(--color-ground)",
              color: "var(--color-ink)",
              borderRadius: 4,
              padding: "7px 10px",
              fontSize: 13,
              fontFamily: "var(--font-mono)",
              minWidth: 180,
            }}
          />
          <button
            type="button"
            disabled={!ready || decide.isPending}
            onClick={() => decide.mutate("approved")}
            style={btn(ready && !decide.isPending, "var(--color-accent)")}
          >
            {decide.isPending ? "Recording…" : "Approve"}
          </button>
          <button
            type="button"
            disabled={!ready || decide.isPending}
            onClick={() => decide.mutate("rejected")}
            style={btn(ready && !decide.isPending, "transparent")}
          >
            Reject
          </button>
        </div>
        {!ready && (
          <div style={{ color: "var(--color-ink-faint)", fontSize: 12, marginTop: 6 }}>
            Nothing is written until this matches. There is no accidental path through this screen.
          </div>
        )}
        {decide.error && <WriteFailure error={decide.error} domain={item.domain} />}
      </div>
    </div>
  );
}

function FigureRow({ figure, stale }: { figure: Figure; stale: boolean }) {
  const shown = effectiveState(figure.state as VerifyState, stale);
  const unverified = shown !== "verified";
  const rec = figure.recomputed_paise;
  const d = drift(figure.claimed_paise, rec);

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        gap: 16,
        flexWrap: "wrap",
        padding: "10px 12px",
        marginBottom: 6,
        borderRadius: 4,
        // A not-recomputed figure is structurally distinct, not just differently worded.
        border: "1px solid var(--color-border)",
        borderLeft: `3px solid ${TONE_BORDER[shown] ?? TONE_BORDER.unbacked}`,
        background: unverified ? "var(--color-surface-sunk)" : "var(--color-surface)",
      }}
    >
      <div>
        <div style={{ fontSize: 13, fontWeight: 400 }}>{figure.label}</div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 4 }}>
          <VerifyChip state={shown} />
          <span className="ident" style={{ color: "var(--color-ink-faint)", fontSize: 11 }}>
            {figure.target}
          </span>
        </div>
        {figure.note && (
          <div style={{ color: "var(--color-ink-faint)", fontSize: 11, marginTop: 4 }}>
            {figure.note}
          </div>
        )}
      </div>
      <div style={{ textAlign: "right" }}>
        <div
          className="tnum"
          style={{ fontSize: 18, fontWeight: 400, letterSpacing: "-0.02em" }}
          title={exactInr(figure.claimed_paise)}
        >
          {inr(figure.claimed_paise)}
        </div>
        {/* Only meaningful when Mahsa actually produced a number; otherwise say so, don't imply. */}
        <div className="tnum" style={{ fontSize: 11, color: "var(--color-ink-faint)" }}>
          {rec === null ? "not recomputed" : `Mahsa recomputed ${inrOrPending(rec)}`}
        </div>
        {d && rec !== null && (
          <div style={{ fontSize: 11, color: "var(--color-verify-unbacked)", marginTop: 2 }}>
            {/* CARDINAL 2: exact paise, ALWAYS. `inr()` here printed "differs by ₹0" for a
                40-paise mismatch — a real drift reading as agreement on the approval screen. */}
            differs by <span className="tnum">{exactInr(d.diffPaise)}</span>
            {d.indistinguishable && (
              <div className="tnum" style={{ color: "var(--color-ink-faint)", marginTop: 2 }}>
                rounded to the rupee these look identical — claimed{" "}
                {exactInr(figure.claimed_paise)}, recomputed {exactInr(rec)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** Receipts survive refetches and route re-renders — a confirmation you can't go back and read is
 *  not a receipt. Rendered above the queue so the last thing you did stays visible. */
function Receipts({ receipts }: { receipts: Receipt[] }) {
  if (receipts.length === 0) return null;
  return (
    <>
      <H2>Recorded this session</H2>
      {receipts.map((r) => {
        // The binding the commit copy promised, now checked instead of asserted.
        const moved = r.shown_state_hash !== undefined && r.shown_state_hash !== r.state_hash;
        return (
          <div
            key={r.audit_hash}
            style={{
              border: `1px solid ${moved ? "var(--color-verify-pending)" : "var(--color-verify)"}`,
              background: "var(--color-surface)",
              borderRadius: 8,
              padding: "14px 16px",
              marginBottom: 8,
              fontSize: 13,
            }}
          >
            <div>
              <strong style={{ fontWeight: 600 }}>{r.domain}</strong> {r.decision} by {r.user_id} —
              sealed to the audit chain.
            </div>
            <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginTop: 6 }}>
              audit hash <span className="ident">{r.audit_hash}</span>
            </div>
            <div style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>
              sealed against books <span className="ident">{r.state_hash}</span>
            </div>
            <div className="tnum" style={{ color: "var(--color-ink-faint)", fontSize: 12 }}>
              {r.timestamp}
            </div>
            {r.shown_state_hash !== undefined &&
              (moved ? (
                <div
                  style={{ color: "var(--color-verify-pending)", fontSize: 12, marginTop: 6 }}
                >
                  The books moved between the figures you read (
                  <span className="ident">{r.shown_state_hash.slice(0, 16)}</span>) and the fold this
                  was sealed against. The hash above is the record, not what was on screen — re-open
                  this domain and check the figures now.
                </div>
              ) : (
                <div style={{ color: "var(--color-verify)", fontSize: 12, marginTop: 6 }}>
                  Same books you were shown — the figures you read are the ones this sealed against.
                </div>
              ))}
          </div>
        );
      })}
    </>
  );
}

/** The 4-question template applied to a WRITE.
 *
 *  ErrorState now has write copy (operation="write"), but it answers generically: "we can't confirm
 *  either way". Here we can do strictly better — a 400 or 503 is the server ANSWERING and refusing,
 *  so we know nothing was written and saying otherwise would be its own small dishonesty. This
 *  component keeps that precision and falls back to ErrorState's exact hedge when we truly have no
 *  response. Do not replace it with a plain <ErrorState operation="write"> — that loses accuracy. */
function WriteFailure({ error, domain }: { error: unknown; domain: string }) {
  const status = error instanceof ApiError ? error.status : null;
  const what =
    status === 503
      ? "Mahsa is unreachable, so the decision was refused rather than sealed against books nobody recomputed."
      : status === 400
        ? "The confirmation text did not match, so nothing was written."
        : status !== null
          ? `The server refused this decision (${status}).`
          : "The request failed before we got an answer back.";
  const safe =
    status !== null
      ? "Yes. The server answered and refused — no decision was recorded and no filing was submitted."
      : "We do not know whether it landed, so we will not claim it either way. Nothing was filed with a statutory portal. Check the audit trail for this domain before retrying — that chain, not this screen, is the record.";

  return (
    <div
      style={{
        border: "1px solid var(--color-verify-unbacked)",
        borderRadius: 4,
        padding: "10px 12px",
        marginTop: 10,
        fontSize: 12,
        lineHeight: 1.55,
      }}
    >
      <div>
        <strong style={{ fontWeight: 600 }}>What happened.</strong> {what}
      </div>
      <div>
        <strong style={{ fontWeight: 600 }}>Is your money and filing safe.</strong> {safe}
      </div>
      <div>
        <strong style={{ fontWeight: 600 }}>What to do next.</strong>{" "}
        {status === 400
          ? `Type ${domain} exactly, then approve again.`
          : "Open the audit trail and confirm whether the decision landed before retrying. If it isn't there, retry is safe."}
      </div>
      <div className="ident" style={{ color: "var(--color-ink-faint)", marginTop: 4 }}>
        ref approve-{domain}-{status ?? "no-response"}
      </div>
    </div>
  );
}

const TONE_BORDER: Record<string, string> = {
  verified: "var(--color-verify)",
  honest_pending: "var(--color-verify-pending)",
  unbacked: "var(--color-verify-unbacked)",
};

function btn(enabled: boolean, background: string): React.CSSProperties {
  return {
    background: enabled ? background : "var(--color-surface-sunk)",
    color:
      enabled && background !== "transparent"
        ? "var(--color-on-accent)"
        : "var(--color-ink-muted)",
    border: background === "transparent" ? "1px solid var(--color-border-strong)" : "none",
    padding: "7px 14px",
    borderRadius: 4,
    fontSize: 13,
    fontWeight: 400,
    fontFamily: "inherit",
    cursor: enabled ? "pointer" : "not-allowed",
  };
}
