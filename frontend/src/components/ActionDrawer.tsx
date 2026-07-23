// P0-2 — the generic action drawer: schema → form → preview panel → explicit confirm.
//
// INVARIANT 9 (docs/MASTER_PLAN.md): every write flow is preview → explicit confirm. The state
// machine below makes the ordering structural, not conventional:
//   · `commitPayload` returns null unless the drawer holds a live server preview — there is no
//     other path to a commit body, so dropping the preview step fails `ActionDrawer.test.ts`.
//   · a commit sends the SERVER's normalized echo + its HMAC token, never the live inputs; the
//     server independently 409s any drift, this just keeps the client honest too.
//   · editing any field after a preview drops the preview (the token no longer describes what
//     the user is looking at).
//
// Keyboard (WS7.4 — a Tally operator never needs the mouse): Enter advances fields; inside a
// `lines` grid Enter advances cells and GROWS the array from its last cell; Cmd/Ctrl+Enter
// previews from the form and confirms from the preview panel.
//
// Shapes mirror api/app/web/api_actions.py exactly. Read that file before changing these.

import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { ErrorState } from "./ErrorState";
import { VerifyChip, type VerifyState } from "./VerifiedNumber";
import { useTraceId } from "../lib/trace";
import type { ActionSpec, FieldSpec, Figure } from "../routes/Domain";

export type ActionPreviewData = {
  domain: string;
  key: string;
  committed: false;
  normalized: Record<string, string>;
  will_create: string;
  figures: Figure[];
  preview_token: string;
};

export type ActionCommitData = {
  domain: string;
  key: string;
  committed: true;
  created: string;
  normalized: Record<string, string>;
  after_figures: Figure[];
};

// ── pure logic (tested in ActionDrawer.test.ts) ──────────────────────────────

export type DrawerPhase =
  | { step: "editing"; values: Record<string, string> }
  | { step: "previewed"; values: Record<string, string>; preview: ActionPreviewData }
  | { step: "committed"; values: Record<string, string>; result: ActionCommitData };

/** One empty row shaped by a lines field's column sub-schema. */
export function emptyRow(columns: FieldSpec[]): Record<string, string> {
  return Object.fromEntries(columns.map((c) => [c.name, ""]));
}

/** Every schema field gets a value slot — the form is derived from the schema, nothing else.
 *  A `lines` field starts as ONE empty row (its value is always a JSON array string — the
 *  same canonical shape the server validates and binds into the preview token). */
export function initialValues(a: ActionSpec): Record<string, string> {
  return Object.fromEntries(
    a.fields.map((f) => [
      f.name,
      f.type === "lines" && f.columns ? JSON.stringify([emptyRow(f.columns)]) : "",
    ]),
  );
}

/** P1-8 (receipt OCR) — a prefill overlaid on the blank form. Only schema-declared field names
 *  survive the overlay, so a parsed field the action doesn't have (or a stray key) can never
 *  reach the server: it is silently absent from the form, not silently written. Prefilled
 *  values land in the SAME editable inputs as manual entry — nothing about the preview/commit
 *  gate below changes for them. */
export function mergedInitialValues(
  a: ActionSpec,
  prefill?: Record<string, string>,
): Record<string, string> {
  const base = initialValues(a);
  if (!prefill) return base;
  const merged = { ...base };
  for (const f of a.fields) {
    if (prefill[f.name]) merged[f.name] = prefill[f.name];
  }
  return merged;
}

/** Backend field type → native control. Unknown types fall to a plain text input, never a
 *  crash and never a guessed richer control. */
export function controlType(type: string): "text" | "number" | "date" | "select" {
  return type === "number" || type === "date" || type === "select" ? type : "text";
}

/** Rows of a lines field's JSON value. Garbage parses to [] — never a crash. */
export function parseLines(value: string): Record<string, string>[] {
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? (parsed as Record<string, string>[]) : [];
  } catch {
    return [];
  }
}

/** Write one cell, materializing missing rows so the visual grid and the value never drift. */
export function setCell(
  value: string,
  columns: FieldSpec[],
  row: number,
  col: string,
  v: string,
): string {
  const rows = parseLines(value);
  while (rows.length <= row) rows.push(emptyRow(columns));
  rows[row] = { ...rows[row], [col]: v };
  return JSON.stringify(rows);
}

export function addRow(value: string, columns: FieldSpec[]): string {
  return JSON.stringify([...parseLines(value), emptyRow(columns)]);
}

/** Enter inside the grid: next cell → next row → GROW the array (WS7.4: arrays add rows). */
export function lineEnterAdvance(
  row: number,
  col: number,
  rowCount: number,
  colCount: number,
): { row: number; col: number } | "addRow" {
  if (col + 1 < colCount) return { row, col: col + 1 };
  if (row + 1 < rowCount) return { row: row + 1, col: 0 };
  return "addRow";
}

/** What the Cmd/Ctrl+Enter chord does per phase: previews the form, confirms the preview,
 *  does nothing on the success panel. The commit path still runs through `commitPayload`,
 *  so the chord can never skip the preview step. */
export function chordAction(step: DrawerPhase["step"]): "preview" | "confirm" | "none" {
  if (step === "previewed") return "confirm";
  if (step === "editing") return "preview";
  return "none";
}

/** A preview figure row is the SERVER's payload verbatim: its formatted value untouched (no
 *  client math on money) and its badge state run through the one gate passed down from
 *  Domain.tsx. There is no other path to a ✓ in this drawer. */
export function figureRow(
  f: Figure,
  badge: (state: string) => VerifyState,
): { key: string; label: string; value: string; state: VerifyState } {
  return { key: f.key, label: f.label, value: f.value, state: badge(f.state) };
}

/** Any edit invalidates a held preview: its token describes values the user no longer sees. */
export function editField(phase: DrawerPhase, name: string, value: string): DrawerPhase {
  const values = phase.step === "committed" ? {} : phase.values;
  return { step: "editing", values: { ...values, [name]: value } };
}

/** The ONLY source of a commit body. Null unless a live preview is held (ordering enforced);
 *  when held, it commits the server's normalized echo + token — never the live inputs. */
export function commitPayload(
  phase: DrawerPhase,
): { values: Record<string, string>; preview_token: string } | null {
  if (phase.step !== "previewed") return null;
  return {
    values: phase.preview.normalized,
    preview_token: phase.preview.preview_token,
  };
}

/** Enter on field i: focus the next field, or fire the preview from the last one. */
export function enterAdvance(index: number, fieldCount: number): number | "preview" {
  return index + 1 < fieldCount ? index + 1 : "preview";
}

/** Cmd/Ctrl+Enter — the confirm chord, and ONLY that chord. */
export function isConfirmKey(e: { key: string; metaKey: boolean; ctrlKey: boolean }): boolean {
  return e.key === "Enter" && (e.metaKey || e.ctrlKey);
}

// ── component ────────────────────────────────────────────────────────────────

export function ActionDrawer({
  domain,
  a,
  badge,
  onCommitted,
  prefill,
}: {
  domain: string;
  a: ActionSpec;
  /** The single badge gate lives in Domain.tsx (`honestState` + mahsa_up); passed in so this
   *  component cannot invent its own path to a ✓. */
  badge: (state: string) => VerifyState;
  onCommitted: () => void;
  /** P1-8 — e.g. receipt-OCR output. Prefills matching fields but changes nothing about the
   *  editable-form / preview-then-confirm contract; a caveat renders while any prefilled value
   *  is still on screen unconfirmed. */
  prefill?: Record<string, string>;
}) {
  const [phase, setPhase] = useState<DrawerPhase>({
    step: "editing",
    values: mergedInitialValues(a, prefill),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const traceId = useTraceId(`action-${domain}-${a.key}`);
  const inputs = useRef<(HTMLInputElement | HTMLSelectElement | null)[]>([]);

  const base = `/domains/${encodeURIComponent(domain)}/actions/${encodeURIComponent(a.key)}`;

  async function preview() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const p = await api<ActionPreviewData>(`${base}/preview`, {
        method: "POST",
        body: JSON.stringify({ values: phase.values }),
      });
      setPhase({ step: "previewed", values: phase.values, preview: p });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    const payload = commitPayload(phase); // structural gate — null means no preview is held
    if (payload === null || busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api<ActionCommitData>(`${base}/commit`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setPhase({ step: "committed", values: {}, result: r });
      onCommitted();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  function onFieldKeyDown(e: React.KeyboardEvent, index: number) {
    if (e.key !== "Enter" || e.metaKey || e.ctrlKey) return;
    e.preventDefault();
    const next = enterAdvance(index, a.fields.length);
    if (next === "preview") void preview();
    else inputs.current[next]?.focus();
  }

  const fieldStyle: React.CSSProperties = {
    width: "100%",
    boxSizing: "border-box",
    border: "1px solid var(--color-border)",
    borderRadius: 4,
    background: "var(--color-surface)",
    color: "var(--color-ink)",
    padding: "5px 8px",
    fontSize: 13,
  };

  return (
    <details
      style={{
        border: "1px solid var(--color-border)",
        background: "var(--color-surface)",
        borderRadius: 4,
        padding: "7px 12px",
        marginBottom: 4,
        fontSize: 13,
      }}
      onKeyDown={(e) => {
        if (isConfirmKey(e)) {
          e.preventDefault();
          // WS7.4: one chord, phase-aware — previews the form, confirms the preview.
          const act = chordAction(phase.step);
          if (act === "confirm") void confirm();
          else if (act === "preview") void preview();
        }
      }}
    >
      <summary style={{ cursor: "pointer", listStyle: "none" }}>
        {a.label}{" "}
        <span className="ident" style={{ color: "var(--color-ink-faint)" }}>
          {a.key}
        </span>
      </summary>

      {phase.step === "committed" ? (
        <div style={{ marginTop: 8, fontSize: 12 }}>
          <p style={{ margin: "0 0 6px", color: "var(--color-ink)" }}>{phase.result.created}</p>
          <p style={{ margin: 0, color: "var(--color-ink-muted)" }}>
            Written to the books — the figures above have been refreshed.
          </p>
          <button
            type="button"
            style={{ ...buttonStyle(false), marginTop: 8 }}
            onClick={() => setPhase({ step: "editing", values: initialValues(a) })}
          >
            Add another
          </button>
        </div>
      ) : (
        <div style={{ marginTop: 8, display: "grid", gap: 6 }}>
          {phase.step === "editing" && prefill && Object.keys(prefill).length > 0 && (
            <p
              style={{
                margin: "0 0 4px",
                fontSize: 11,
                color: "var(--color-accent)",
                background: "var(--color-accent-sunk)",
                border: "1px solid var(--color-border-strong)",
                borderRadius: 4,
                padding: "5px 8px",
              }}
            >
              Parsed from receipt — check before submitting:{" "}
              {a.fields
                .filter((f) => prefill[f.name])
                .map((f) => f.label)
                .join(", ")}
              . OCR is never authoritative — edit anything that looks wrong.
            </p>
          )}
          {a.fields.map((f, i) => (
            <label key={f.name} style={{ fontSize: 12, color: "var(--color-ink-muted)" }}>
              {f.label}
              {f.required ? "" : " (optional)"}
              {f.type === "lines" && f.columns ? (
                <LinesEditor
                  columns={f.columns}
                  value={phase.values[f.name] ?? ""}
                  onChange={(v) => setPhase((p) => editField(p, f.name, v))}
                  firstCellRef={(el) => {
                    inputs.current[i] = el; // Enter from the previous field lands in the grid
                  }}
                  fieldStyle={fieldStyle}
                />
              ) : controlType(f.type) === "select" ? (
                <select
                  ref={(el) => {
                    inputs.current[i] = el;
                  }}
                  value={phase.values[f.name] ?? ""}
                  onChange={(e) => setPhase((p) => editField(p, f.name, e.target.value))}
                  onKeyDown={(e) => onFieldKeyDown(e, i)}
                  style={fieldStyle}
                >
                  <option value="">— choose —</option>
                  {f.options.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  ref={(el) => {
                    inputs.current[i] = el;
                  }}
                  type={controlType(f.type)}
                  value={phase.values[f.name] ?? ""}
                  placeholder={f.placeholder}
                  onChange={(e) => setPhase((p) => editField(p, f.name, e.target.value))}
                  onKeyDown={(e) => onFieldKeyDown(e, i)}
                  style={fieldStyle}
                />
              )}
            </label>
          ))}

          {error !== null && (
            <ErrorState error={error} traceId={traceId} operation="write" />
          )}

          {phase.step === "previewed" ? (
            <div
              style={{
                border: "1px solid var(--color-border-strong)",
                background: "var(--color-surface-sunk)",
                borderRadius: 4,
                padding: "8px 10px",
              }}
            >
              <div
                style={{
                  fontSize: 10,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color: "var(--color-ink-faint)",
                  marginBottom: 4,
                }}
              >
                Preview — nothing written yet
              </div>
              <p style={{ margin: "0 0 6px", fontSize: 12 }}>{phase.preview.will_create}</p>
              {Object.entries(phase.preview.normalized)
                .filter(([, v]) => v !== "")
                .map(([k, v]) => (
                  <div
                    key={k}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: 12,
                      color: "var(--color-ink-muted)",
                    }}
                  >
                    <span className="ident">{k}</span>
                    <span className="tnum">{v}</span>
                  </div>
                ))}
              {phase.preview.figures.map((f) => {
                // Payload in, badge through the one gate — never client math (§0.4).
                const row = figureRow(f, badge);
                return (
                  <div
                    key={row.key}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 8,
                      fontSize: 12,
                      marginTop: 4,
                    }}
                  >
                    <span>{row.label}</span>
                    <span>
                      <span className="tnum" style={{ marginRight: 8 }}>
                        {row.value}
                      </span>
                      <VerifyChip state={row.state} />
                    </span>
                  </div>
                );
              })}
              <div style={{ display: "flex", gap: 8, marginTop: 8, alignItems: "center" }}>
                <button type="button" style={buttonStyle(true)} disabled={busy} onClick={confirm}>
                  Confirm — write to the books
                </button>
                <span style={{ fontSize: 11, color: "var(--color-ink-faint)" }}>⌘/Ctrl+Enter</span>
              </div>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button type="button" style={buttonStyle(false)} disabled={busy} onClick={preview}>
                Preview
              </button>
              <span style={{ fontSize: 11, color: "var(--color-ink-faint)" }}>
                Nothing is written until you confirm the preview.
              </span>
            </div>
          )}
        </div>
      )}
    </details>
  );
}

/** P0-3 — the multi-row grid behind a `lines` field. Its single source of truth is the
 *  field's JSON-array string value (what the server validates and the token binds), so
 *  every cell edit writes through `setCell` and the grid re-derives from the value.
 *  Keyboard: Enter advances cell → row → adds a row from the last cell; Tab works natively. */
function LinesEditor({
  columns,
  value,
  onChange,
  firstCellRef,
  fieldStyle,
}: {
  columns: FieldSpec[];
  value: string;
  onChange: (v: string) => void;
  firstCellRef: (el: HTMLInputElement | null) => void;
  fieldStyle: React.CSSProperties;
}) {
  const parsed = parseLines(value);
  const rows = parsed.length ? parsed : [emptyRow(columns)];
  const cells = useRef<Record<string, HTMLInputElement | null>>({});
  const pendingFocus = useRef<string | null>(null);
  useEffect(() => {
    if (pendingFocus.current) {
      cells.current[pendingFocus.current]?.focus();
      pendingFocus.current = null;
    }
  });

  function grow() {
    pendingFocus.current = `${rows.length}-0`;
    onChange(addRow(JSON.stringify(rows), columns));
  }

  function onCellKeyDown(e: React.KeyboardEvent, row: number, col: number) {
    if (e.key !== "Enter" || e.metaKey || e.ctrlKey) return;
    e.preventDefault();
    const next = lineEnterAdvance(row, col, rows.length, columns.length);
    if (next === "addRow") grow();
    else cells.current[`${next.row}-${next.col}`]?.focus();
  }

  return (
    <div style={{ marginTop: 4 }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${columns.length}, 1fr)`,
          gap: 4,
        }}
      >
        {columns.map((c) => (
          <span
            key={c.name}
            style={{
              fontSize: 10,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              color: "var(--color-ink-faint)",
            }}
          >
            {c.label}
            {c.required ? "" : " (opt)"}
          </span>
        ))}
        {rows.map((r, ri) =>
          columns.map((c, ci) => (
            <input
              key={`${ri}-${c.name}`}
              ref={(el) => {
                cells.current[`${ri}-${ci}`] = el;
                if (ri === 0 && ci === 0) firstCellRef(el);
              }}
              type={controlType(c.type) === "number" ? "number" : "text"}
              value={r[c.name] ?? ""}
              placeholder={c.placeholder}
              onChange={(e) => onChange(setCell(JSON.stringify(rows), columns, ri, c.name, e.target.value))}
              onKeyDown={(e) => onCellKeyDown(e, ri, ci)}
              style={fieldStyle}
            />
          )),
        )}
      </div>
      <button type="button" style={{ ...buttonStyle(false), marginTop: 4 }} onClick={grow}>
        + Add row <span style={{ color: "var(--color-ink-faint)" }}>(or Enter in the last cell)</span>
      </button>
    </div>
  );
}

function buttonStyle(primary: boolean): React.CSSProperties {
  return {
    border: `1px solid ${primary ? "var(--color-accent)" : "var(--color-border-strong)"}`,
    background: primary ? "var(--color-accent)" : "var(--color-surface)",
    color: primary ? "var(--color-on-accent)" : "var(--color-ink)",
    borderRadius: 4,
    padding: "5px 12px",
    fontSize: 12,
    cursor: "pointer",
  };
}
