// WS7 — the Audit Room, the CA's default landing (app/core/landing.py ROLE_LANDING.CA).
// Reads GET /api/audit (app/web/api_domains.py::audit_json) — a pure re-derivation, never a
// re-verification done client side: `chain_intact` IS the server's `verify_chain(load_chain())`
// result, so this screen can never show a green chip over a chain the server itself flagged.
//
// This screen's whole job (per the ticket) is to let a CA satisfy themselves nothing was
// altered. Design for scrutiny: hashes in mono, newest-first, paging, and a chain-verification
// result that is unmissable — especially, ONLY especially, when it fails. A quietly-rendered
// tamper failure is worse than no audit log at all, so a broken chain gets the loudest, largest,
// most structurally distinct treatment on the page — not a small chip alongside the good state.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { ErrorState } from "../components/ErrorState";
import { Header, H2, Empty } from "./Today";

export type AuditEntry = {
  timestamp: string;
  action: string;
  domain: string;
  user_id: string;
  query: string | null;
  validation_status: string;
  rules_version: string | null;
  prev_hash: string;
  this_hash: string;
};

type AuditData = {
  chain_intact: boolean;
  total: number;
  limit: number;
  offset: number;
  entries: AuditEntry[];
};

// ── pure logic (tested in AuditRoom.test.ts) ─────────────────────────────────

export type ChainBanner = {
  tone: "intact" | "broken";
  headline: string;
  detail: string;
};

/** The single honesty gate on this screen: the tone can ONLY come from the server's own
 *  `chain_intact` result, never re-derived or softened here. */
export function chainBanner(intact: boolean, total: number): ChainBanner {
  if (!intact) {
    return {
      tone: "broken",
      headline: "CHAIN VERIFICATION FAILED",
      detail:
        "The hash chain does not reconstruct: at least one entry's hash no longer matches its predecessor. This means an entry was altered, deleted, or reordered after being sealed. Do not treat any figure on this system as verified until this is investigated.",
    };
  }
  return {
    tone: "intact",
    headline: "Chain verified",
    detail: `All ${total} entr${total === 1 ? "y" : "ies"} in the log were re-hashed just now and each one's hash correctly follows from its predecessor. Nothing here has been altered since it was sealed.`,
  };
}

/** Paging arithmetic for a page of `limit` starting at `offset`, out of `total`. Pulled out so
 *  the off-by-one at the edges (empty log, partial last page) is tested, not eyeballed. */
export function pageInfo(total: number, limit: number, offset: number) {
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  return {
    from,
    to,
    hasPrev: offset > 0,
    hasNext: offset + limit < total,
    prevOffset: Math.max(0, offset - limit),
    nextOffset: offset + limit,
  };
}

// ── screen ───────────────────────────────────────────────────────────────────

const PAGE_SIZE = 50;

export function AuditRoom() {
  const [offset, setOffset] = useState(0);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["audit", offset],
    queryFn: () => api<AuditData>(`/audit?limit=${PAGE_SIZE}&offset=${offset}`),
  });

  if (isLoading && !data) return <p style={{ color: "var(--color-ink-muted)" }}>Loading…</p>;

  if (error) {
    return (
      <div>
        <Header title="Audit Room" />
        <ErrorState error={error} traceId={`audit-${Date.now().toString(36)}`} onRetry={refetch} />
      </div>
    );
  }
  if (!data) return null;

  const banner = chainBanner(data.chain_intact, data.total);
  const page = pageInfo(data.total, data.limit, data.offset);

  return (
    <section>
      <Header title="Audit Room" />

      <ChainVerificationBanner banner={banner} />

      <H2>
        Hash-chained log · {data.total} entr{data.total === 1 ? "y" : "ies"}
      </H2>

      {data.entries.length === 0 ? (
        <Empty>Nothing has been sealed to the audit chain yet.</Empty>
      ) : (
        <>
          <div style={{ color: "var(--color-ink-faint)", fontSize: 12, marginBottom: 8 }}>
            Newest first · showing {page.from}–{page.to} of {data.total}
          </div>
          {data.entries.map((e, i) => (
            <EntryRow key={`${e.this_hash}-${i}`} entry={e} />
          ))}
          <Pager
            page={page}
            onPrev={() => setOffset(page.prevOffset)}
            onNext={() => setOffset(page.nextOffset)}
          />
        </>
      )}
    </section>
  );
}

/** The most important element on the screen when the chain is broken — large, alone at the
 *  top, structurally distinct (not just a red chip) from every other surface in the product. */
function ChainVerificationBanner({ banner }: { banner: ChainBanner }) {
  const broken = banner.tone === "broken";
  return (
    <div
      role={broken ? "alert" : undefined}
      style={{
        border: `1px solid ${broken ? "var(--color-verify-unbacked)" : "var(--color-verify)"}`,
        borderLeft: `5px solid ${broken ? "var(--color-verify-unbacked)" : "var(--color-verify)"}`,
        background: broken ? "var(--color-verify-unbacked)" : "var(--color-surface)",
        color: broken ? "#fff" : "var(--color-ink)",
        borderRadius: 8,
        padding: broken ? "20px 22px" : "14px 16px",
        marginBottom: 20,
      }}
    >
      <div
        style={{
          fontSize: broken ? 20 : 15,
          fontWeight: 500,
          letterSpacing: broken ? "0.02em" : "-0.01em",
        }}
      >
        {broken ? "⚠ " : "✓ "}
        {banner.headline}
      </div>
      <div
        style={{
          fontSize: 13,
          lineHeight: 1.55,
          marginTop: 6,
          color: broken ? "rgba(255,255,255,0.92)" : "var(--color-ink-muted)",
        }}
      >
        {banner.detail}
      </div>
    </div>
  );
}

function EntryRow({ entry }: { entry: AuditEntry }) {
  return (
    <div
      style={{
        border: "1px solid var(--color-border)",
        borderRadius: 8,
        padding: "12px 16px",
        marginBottom: 8,
        background: "var(--color-surface)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div>
          <strong style={{ fontSize: 14 }}>{entry.action}</strong>
          <span style={{ color: "var(--color-ink-muted)", fontSize: 13 }}> · {entry.domain}</span>
        </div>
        <div className="tnum" style={{ color: "var(--color-ink-faint)", fontSize: 12 }}>
          {entry.timestamp}
        </div>
      </div>
      <div style={{ color: "var(--color-ink-muted)", fontSize: 12, marginTop: 4 }}>
        by {entry.user_id}
        {entry.query && <> · {entry.query}</>}
        {" · "}
        status {entry.validation_status || "—"}
        {entry.rules_version && <> · rules {entry.rules_version}</>}
      </div>
      <div style={{ fontSize: 11, marginTop: 8, color: "var(--color-ink-faint)" }}>
        <div>
          prev <span className="ident">{entry.prev_hash}</span>
        </div>
        <div>
          this <span className="ident">{entry.this_hash}</span>
        </div>
      </div>
    </div>
  );
}

function Pager({
  page,
  onPrev,
  onNext,
}: {
  page: ReturnType<typeof pageInfo>;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
      <button
        type="button"
        disabled={!page.hasPrev}
        onClick={onPrev}
        style={pagerBtn(page.hasPrev)}
      >
        ← Newer
      </button>
      <button
        type="button"
        disabled={!page.hasNext}
        onClick={onNext}
        style={pagerBtn(page.hasNext)}
      >
        Older →
      </button>
    </div>
  );
}

function pagerBtn(enabled: boolean): React.CSSProperties {
  return {
    background: "transparent",
    border: "1px solid var(--color-border-strong)",
    color: enabled ? "var(--color-ink)" : "var(--color-ink-faint)",
    padding: "6px 12px",
    borderRadius: 4,
    fontSize: 13,
    fontFamily: "inherit",
    cursor: enabled ? "pointer" : "not-allowed",
  };
}
