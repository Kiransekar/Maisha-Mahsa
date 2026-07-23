// The verification chip + working panel — the unit of trust in the product.
//
// BLEND (docs/WS7_BUILD_CONTRACT.md):
//   · BRAND_THEME §4  — "the verification chip is the logo"; verification hues never money hues
//   · UX research T1  — badge state comes from the payload, so a fabricated ✓ is impossible here
//   · UX research T7  — every badged figure must be INTERROGABLE: inputs → formula → citations →
//                       documents → verdict hash → report-issue. A tooltip is not a working panel.
//   · UX research T4  — a figure computed on stale inputs downgrades to ◐. Never a ✓ on stale data.
//
// Uses native <details> (no JS, mirrors the HTMX WS7.2 implementation) so the two surfaces stay
// behaviourally identical.

export type VerifyState = "verified" | "honest_pending" | "unbacked";

export type Working = {
  inputs?: { label: string; value: string }[];
  formula?: string | null;
  citations?: { text: string; url?: string | null }[];
  documents?: { label: string }[];
  verdict_hash?: string | null;
  rule_pack_version?: string | null;
  note?: string | null;
};

const MARK: Record<VerifyState, { glyph: string; label: string; color: string; title: string }> = {
  verified: {
    glyph: "✓",
    label: "recomputed",
    color: "var(--color-verify)",
    title: "Mahsa independently recomputed this figure and it matched to the paisa.",
  },
  honest_pending: {
    glyph: "◐",
    label: "not yet sealed",
    color: "var(--color-verify-pending)",
    title: "Not yet recomputed by Mahsa. Shown as-is — not a verified figure.",
  },
  unbacked: {
    glyph: "✕",
    label: "unbacked",
    color: "var(--color-verify-unbacked)",
    title: "This figure could not be backed by a recomputation.",
  },
};

/**
 * Freshness of the inputs behind a figure. "unknown" is NOT the same fact as "stale" — we could
 * not check. Both fail closed (a ✓ downgrades either way), but only one of them may be stated as
 * fact to the user. Conflating them was itself a fabricated claim.
 */
export type Freshness = boolean | "unknown";

/** T4: a ✓ is only honest if the inputs are fresh. Staleness downgrades the badge, never hides. */
export function effectiveState(state: VerifyState, stale: Freshness): VerifyState {
  // Fail closed: unknown freshness cannot sustain a ✓ any more than known staleness can.
  return stale !== false && state === "verified" ? "honest_pending" : state;
}

export function VerifyChip({ state }: { state: VerifyState }) {
  const m = MARK[state] ?? MARK.unbacked; // an unknown state is never optimistically ✓
  return (
    <span style={{ color: m.color, fontSize: 12, whiteSpace: "nowrap" }} title={m.title}>
      {m.glyph} {m.label}
    </span>
  );
}

/** T7: the drill-down. Renders only what the server actually sent — never a fabricated trail. */
function WorkingPanel({ working, state }: { working: Working; state: VerifyState }) {
  const { inputs = [], formula, citations = [], documents = [], verdict_hash } = working;
  const empty = !inputs.length && !formula && !citations.length && !documents.length;

  return (
    <details style={{ marginTop: 8 }}>
      <summary
        style={{
          cursor: "pointer",
          fontSize: 12,
          color: "var(--color-ink-muted)",
          listStyle: "none",
        }}
      >
        Show working
      </summary>
      <div
        style={{
          marginTop: 8,
          paddingTop: 8,
          borderTop: "1px solid var(--color-border)",
          fontSize: 12,
          color: "var(--color-ink-muted)",
        }}
      >
        {empty && (
          <p style={{ margin: "0 0 8px" }}>
            No working has been sealed for this figure yet — that is why it reads ◐ rather than ✓.
          </p>
        )}

        {inputs.length > 0 && (
          <Block title="Inputs">
            {inputs.map((i) => (
              <div key={i.label} style={{ display: "flex", justifyContent: "space-between" }}>
                <span>{i.label}</span>
                <span className="tnum">{i.value}</span>
              </div>
            ))}
          </Block>
        )}

        {formula && (
          <Block title="Formula">
            <code className="ident">{formula}</code>
          </Block>
        )}

        {citations.length > 0 && (
          <Block title="Citations">
            {citations.map((c, i) => (
              <div key={i}>
                {c.url ? (
                  <a href={c.url} style={{ color: "var(--color-accent)" }}>
                    {c.text}
                  </a>
                ) : (
                  c.text
                )}
              </div>
            ))}
          </Block>
        )}

        {documents.length > 0 && (
          <Block title="Documents">
            {documents.map((d, i) => (
              <div key={i}>{d.label}</div>
            ))}
          </Block>
        )}

        <Block title="Verdict">
          {verdict_hash ? (
            <span className="ident">{verdict_hash}</span>
          ) : (
            <span>Not yet sealed to the audit chain.</span>
          )}
        </Block>

        {/* T6/T7: an escape hatch on every figure — disputing a number is a first-class action. */}
        <a
          href={`/inbox?report=${encodeURIComponent(verdict_hash ?? "unsealed")}`}
          style={{ color: "var(--color-accent)", fontSize: 12 }}
        >
          This number looks wrong →
        </a>
        {state === "verified" && (
          <div style={{ color: "var(--color-ink-faint)", marginTop: 6 }}>
            Recomputed independently by Mahsa. If you disagree, the working above is the whole
            basis — nothing else went into it.
          </div>
        )}
      </div>
    </details>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div
        style={{
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          fontSize: 10,
          color: "var(--color-ink-faint)",
          marginBottom: 2,
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

// ── T11 field-level RBAC: restricted fields ──────────────────────────────────
// The server strips a sensitive value at its serialization boundary and sends this shape
// instead (app/core/landing.mask_field). The value never reached the browser; this component
// makes the restriction VISIBLE — hidden-not-absent violates the WS7 contract.

export type RestrictedField = {
  restricted: true;
  reason: string;
  target?: string;
  key?: string;
  label?: string;
};

/** Type guard for the exact server shape — anything else renders as a normal payload. */
export function isRestricted(x: unknown): x is RestrictedField {
  return (
    typeof x === "object" && x !== null && (x as { restricted?: unknown }).restricted === true
  );
}

/** The lock chip: states that a field exists and why this role cannot see it. Never blank. */
export function LockChip({ reason }: { reason: string }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        border: "1px solid var(--color-border-strong)",
        borderRadius: 4,
        padding: "2px 8px",
        fontSize: 12,
        color: "var(--color-ink-muted)",
        whiteSpace: "nowrap",
      }}
      title="This field is restricted for your role. The value was removed on the server — it was never sent to this browser."
    >
      <span aria-hidden="true">🔒</span> restricted — {reason}
    </span>
  );
}

/** A labelled figure, its verification state, and its full working. */
export function VerifiedNumber({
  label,
  value,
  state,
  note,
  working,
  asOf,
  stale = false,
  spark,
}: {
  label: string;
  value: string;
  state: VerifyState;
  note?: string | null;
  working?: Working;
  asOf?: string;
  stale?: Freshness;
  // P2-3: an optional trend sparkline (Sparkline component) — a figure with no real ≥2-point
  // history simply omits this prop, so the card carries no trend, not a fabricated flat one.
  spark?: React.ReactNode;
}) {
  const shown = effectiveState(state, stale);
  return (
    <div
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)", // borders, not shadows (BRAND_THEME §3)
        borderRadius: 8,
        padding: "14px 16px",
        minWidth: 220,
        flex: "1 1 220px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div style={{ color: "var(--color-ink-muted)", fontSize: 12 }}>{label}</div>
        {spark}
      </div>
      <div className="tnum" style={{ fontSize: 24, letterSpacing: "-0.02em", margin: "4px 0 6px" }}>
        {value}
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <VerifyChip state={shown} />
        {asOf && (
          <span className="tnum" style={{ color: "var(--color-ink-faint)", fontSize: 11 }}>
            as of {asOf}
          </span>
        )}
      </div>
      {/* T4: say WHY it was downgraded — a silent downgrade is its own trust failure. But say only
          what is true: "stale" and "we could not check" are different facts and read differently. */}
      {stale !== false && state === "verified" && (
        <div style={{ color: "var(--color-verify-pending)", fontSize: 11, marginTop: 6 }}>
          {stale === "unknown"
            ? "Downgraded from ✓: we couldn't check how fresh the inputs behind this figure are, so we won't claim it is still verified."
            : "Downgraded from ✓: the inputs behind this figure are stale, so the recomputation no longer stands."}
        </div>
      )}
      {note ? (
        <div style={{ color: "var(--color-ink-faint)", fontSize: 11, marginTop: 6 }}>{note}</div>
      ) : null}
      {working && <WorkingPanel working={working} state={shown} />}
    </div>
  );
}
