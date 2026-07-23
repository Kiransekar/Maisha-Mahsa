// P1-1 — Ask Maisha SPA screen. Mirrors the HTMX /ask page (app/web/templates/ask.html): a
// question box -> answer card, reading POST /api/ask (app.web.api_domains::ask_json), a thin
// wrapper over the SAME app.core.ask.answer_query pipeline the HTMX surface calls — so a
// figure's verdict can never drift between the two surfaces.
//
// Honesty rules carried from the server, never re-decided here:
//   · every figure's ✓/◐/✕ state comes from the payload's per-figure FigureVerdict, never
//     re-derived client-side
//   · a narrative containing a number NOT in `figures` is a server-side contract (app.llm.retry's
//     verified-generation loop) — this screen renders exactly what the payload states, it does
//     not re-verify the narrative text
//   · Mahsa down is an explicit note, not a silently thinner answer

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useTraceId } from "../lib/trace";
import { VerifiedNumber, type VerifyState, type Working } from "../components/VerifiedNumber";
import { ErrorState } from "../components/ErrorState";
import { Header, H2, Empty } from "./Today";

type AskFigure = { label: string; value: string; state: string };
// SPEC-MEMCITE-1.0 §B1/§B4.3 (CITE.P1-2): a cell-level anchor riding an Ask citation — the
// server mints it only where a figure derives from an anchored source row; absent otherwise.
export type AskAnchor = {
  doc_sha256: string;
  file_name: string;
  locator: { kind: string; source_row?: number };
  row_hash: string;
  occurrence: number;
  excerpt: string;
  resolution?: "resolved" | "moved" | "broken";
  note?: string | null;
  url?: string | null;
};
type AskCitation = {
  rule_id: string;
  text: string;
  citation: string;
  domain: string;
  anchor?: AskAnchor | null;
};
type AskAnswer = {
  query: string;
  domain: string | null;
  narrative: string;
  figures: AskFigure[];
  citations: AskCitation[];
  status: string | null;
  requires_approval: boolean;
  abstained: boolean;
  mahsa_up: boolean;
  provenance: string;
};

const SUGGESTIONS = [
  "What's our runway?",
  "Is our GSTR-3B filing on time?",
  "Any MSME payments overdue?",
  "What's the minimum net pay?",
];

/** The server's `state` string, coerced to a VerifyState. Fails closed: any value this screen
 *  doesn't recognise renders as "unbacked" (✕) — never "verified" — same fail-closed rule
 *  VerifyChip already applies to an unrecognised state. */
export function toVerifyState(raw: string): VerifyState {
  return raw === "verified" || raw === "honest_pending" || raw === "unbacked" ? raw : "unbacked";
}

/** CITE.P1-2: the working panel for an answer's figures. Every citation stays a text line;
 *  anchored ones ALSO become Documents entries — excerpt, /d/vault deep-link and §B2
 *  resolution state — so a broken anchor downgrades the badge via `hasBrokenCitation`,
 *  exactly as on every other surface. No citations -> no panel (never a fabricated trail). */
export function askWorking(citations: AskCitation[]): Working | undefined {
  if (!citations.length) return undefined;
  return {
    citations: citations.map((c) => ({ text: `${c.rule_id} · ${c.citation}` })),
    documents: citations.flatMap((c) =>
      c.anchor
        ? [
            {
              label: c.anchor.excerpt,
              url: c.anchor.url,
              resolution: c.anchor.resolution,
              note: c.anchor.note,
            },
          ]
        : [],
    ),
  };
}

export function Ask() {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<string | null>(null);
  const traceId = useTraceId("ask");

  const ask = useMutation({
    mutationFn: (q: string) =>
      api<AskAnswer>("/ask", { method: "POST", body: JSON.stringify({ q }) }),
  });

  const submit = (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) return;
    setAsked(trimmed);
    ask.mutate(trimmed);
  };

  return (
    <section>
      <Header title="Ask Maisha" />
      <p style={{ color: "var(--color-ink-muted)", fontSize: 13, marginBottom: 20 }}>
        Ask anything about your finances. Every figure is recomputed and validated before you see
        it — a number the engines can&apos;t back is flagged, never shown as fact.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
        style={{ display: "flex", gap: 8, marginBottom: 18 }}
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question…"
          aria-label="Ask Maisha"
          style={{
            flex: 1,
            padding: "9px 12px",
            borderRadius: 4,
            border: "1px solid var(--color-border-strong)",
            background: "var(--color-surface)",
            color: "var(--color-ink)",
            fontSize: 14,
            fontFamily: "inherit",
          }}
        />
        <button
          type="submit"
          disabled={ask.isPending || !question.trim()}
          style={{
            background: "var(--color-accent)",
            color: "#fff",
            border: "none",
            padding: "9px 16px",
            borderRadius: 4,
            fontSize: 13,
            cursor: ask.isPending ? "default" : "pointer",
            fontFamily: "inherit",
          }}
        >
          {ask.isPending ? "Asking…" : "Ask"}
        </button>
      </form>

      {asked === null && (
        <div>
          <div
            style={{
              color: "var(--color-ink-faint)",
              fontSize: 11,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              marginBottom: 8,
            }}
          >
            Try asking
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => {
                  setQuestion(s);
                  submit(s);
                }}
                style={{
                  background: "var(--color-surface-sunk)",
                  border: "1px solid var(--color-border)",
                  borderRadius: 9999,
                  padding: "6px 12px",
                  fontSize: 12,
                  cursor: "pointer",
                  fontFamily: "inherit",
                  color: "var(--color-ink-muted)",
                }}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {ask.isError && (
        <div style={{ marginTop: 16 }}>
          <ErrorState
            error={ask.error}
            traceId={traceId}
            onRetry={() => asked && ask.mutate(asked)}
          />
        </div>
      )}

      {ask.data && <AnswerCard answer={ask.data} />}
    </section>
  );
}

function AnswerCard({ answer }: { answer: AskAnswer }) {
  // The HTMX answer_card.html reuses the SAME citations list as the working panel for every
  // figure (it has no per-figure citation split) — mirrored here rather than inventing one.
  const working = askWorking(answer.citations);

  return (
    <div style={{ marginTop: 20 }}>
      <div style={{ color: "var(--color-ink-faint)", fontSize: 11 }}>{answer.provenance}</div>
      <div style={{ fontSize: 14, margin: "6px 0 12px", color: "var(--color-ink-muted)" }}>
        &ldquo;{answer.query}&rdquo;
      </div>

      {!answer.mahsa_up && <MahsaDownNote />}

      {answer.narrative && <p style={{ fontSize: 14, lineHeight: 1.55 }}>{answer.narrative}</p>}

      {answer.abstained && answer.figures.length === 0 && (
        <Empty>Not enough data to answer confidently — add the underlying records first.</Empty>
      )}

      {answer.figures.length > 0 && (
        <>
          <H2>Figures</H2>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {answer.figures.map((f, i) => (
              <VerifiedNumber
                key={`${f.label}-${i}`}
                label={f.label}
                value={f.value}
                state={toVerifyState(f.state)}
                working={working}
              />
            ))}
          </div>
        </>
      )}

      {answer.status && (
        <div style={{ marginTop: 14, fontSize: 13 }}>
          <StatusPill status={answer.status} />
          {answer.requires_approval && (
            <span style={{ color: "var(--color-ink-muted)", marginLeft: 8 }}>
              · requires approval
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const color =
    status === "red"
      ? "var(--color-verify-unbacked)"
      : status === "yellow"
        ? "var(--color-verify-pending)"
        : "var(--color-verify)";
  return (
    <span
      style={{
        border: `1px solid ${color}`,
        color,
        borderRadius: 9999,
        padding: "3px 10px",
        fontSize: 12,
        textTransform: "uppercase",
        letterSpacing: "0.04em",
      }}
    >
      {status}
    </span>
  );
}

function MahsaDownNote() {
  return (
    <div
      style={{
        border: "1px solid var(--color-verify-unbacked)",
        background: "var(--color-surface)",
        borderRadius: 8,
        padding: "10px 14px",
        marginBottom: 12,
        fontSize: 13,
      }}
    >
      Mahsa is unreachable — figures below are shown as-is, not independently recomputed.
    </div>
  );
}
