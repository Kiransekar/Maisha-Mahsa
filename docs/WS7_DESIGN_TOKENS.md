# WS7.1 — Design-System Foundation (tokens + component states)

Foundation layer for the WS7 UI build. Tokens live in
`api/app/web/static/css/tokens.css`; the money renderer in `api/app/web/format.py`; the
CI money-format gate in `scripts/check_money_format.sh`. Grounded in
`docs/WS7_UX_RESEARCH.md` (81 verified findings) and `docs/MASTER_PLAN.md §9 (WS7.1)`.

## 1 · The verification-vs-money colour rule (the load-bearing decision)

**Verification state and money direction are two different questions and MUST use two
different colour families.**

- **Money direction / cash health** — the sacred Mahsa traffic-light: `--c-green` (up / safe),
  `--c-amber` (at-risk), `--c-red` (down / over-limit).
- **Verification state** — a distinct cool family, `--c-verify*`:

  | State | Glyph | Token | Hue | Means |
  |-------|-------|-------|-----|-------|
  | Verified | ✓ | `--c-verify` | teal | Mahsa recomputed this figure and matched to the paisa |
  | Honest-pending | ◐ | `--c-verify-pending` | indigo | Mahsa cannot yet recompute this target (§0.4) — shown as-is, not endorsed |
  | Unbacked / blocked | ✕ | `--c-verify-fail` | violet | No verified figure behind it, or the verdict was BLOCKED — **not** money-red |

**Why (research grounding).** `WS7_UX_RESEARCH.md` T1 ("numbers silently drift under you") is
the #1 MSME fear and the exact failure the badge exists to kill; the WS7.1 row states the badge
must express a *verification* state (fresh/stale/provisional) **distinct from** *money
direction* — "conflating them is exactly how trust products confuse users." The WS7.V
badge-comprehension gate explicitly tests that owners read ✓/◐/✕ shield + teal/indigo as
verification and do **not** confuse ◐ with money-red. Hence: no `--c-verify*` value may equal a
`--c-green`/`--c-red` value, and a ✕ verification failure is violet, never the money-red used
for "cash down".

**Invariant:** an unverified figure renders ◐ (honest-pending), never ✓. Badge data comes only
from `app/core/verify.py` (`FigureVerdict`), `app/core/verdict.py` (`Verdict`), and
`app/core/mahsa_coverage.py` (`badge_state`) — never fabricated in the template.

## 2 · Money rendering

One renderer, Indian lakh/crore grouping, tabular numerals for aligned columns.

- Canonical function: `app/web/format.py::inr(paise)` / `inr_rupees(rupees)` → `₹12,34,567.00`
  (crore-aware, negatives, zero, paise). Delegates to the ported `Paise.format_inr`
  (`app/core/money.py`, mirror of `dif/src/money.rs`). `fmt_value` and the `rupees` Jinja
  filter both route through it.
- Alignment: apply `.tnum` (or `font-variant-numeric: tabular-nums`) to any money column so
  digits are equal-width and decimals line up. `.figrow__val` already does.
- **CI gate `scripts/check_money_format.sh`** fails the build on any bypass: JS
  `toLocaleString` in `app/web`, `₹{{ … }}` glued in a template, Western `:,.2f` grouping in a
  template money expression, or a hand-rolled `f"…₹{value}…"` in Python outside the two
  canonical renderers. Grounds T9/T10 (lakh/crore is table-stakes for the Indian audience).

  **Known pre-existing debt baselined in the gate** (outside WS7.1 scope — hand to owners):
  `app/domains/gst/eway.py` (Western `:,.2f` grouping in e-way narrative strings, WS1.D7) and
  `app/web/actions.py:79` (raw `₹{amount}` toast, no grouping). Both should switch to
  `format.inr_rupees`; remove the baseline entry when fixed.

## 3 · Component-states inventory

What every shared component looks like in each state — the checklist WS7.2–WS7.7 wire against.

### Verification badge / shield (`.vmark`) — **needs re-wiring in `app.css`**
`app/web/templates` currently uses `.vmark--ok/--pending/--warn`; `app/web/static/css/app.css`
colours `.vmark--ok` with `--c-green` (money green) and `.vmark--warn` with `--c-amber`. **That
is the bug WS7.1 diagnoses** (verification painted in money colours). WS7.2 must repoint them to
the verification family — `app.css` is outside WS7.1's edit scope, so the tokens are provided
here for that ticket to consume:

| Class | Now (wrong) | Target token | Glyph |
|-------|-------------|--------------|-------|
| `.vmark--ok` | `--c-green` | `--c-verify` (teal) | ✓ |
| `.vmark--pending` | `--c-text-muted` | `--c-verify-pending` (indigo) | ◐ |
| `.vmark--warn` | `--c-amber` | `--c-verify-fail` (violet) | ✕ |

(The teal glow at `app.css:268` should also move from `rgba(52,211,153…)` to `--c-verify-glow`.)

### Money figure (`.figrow__val`, KPI value)
- default: tabular-nums, right-aligned, `₹` Indian-grouped via `inr`.
- with badge: figure + trailing verification shield (teal ✓ / indigo ◐ / violet ✕).
- direction colour (green/red) may tint the figure for cash up/down — orthogonal to the shield.

### Status pill / chip (`.chip`, `.pill`) — money/traffic-light family
- neutral / `--chip--red` (over-limit) / green (safe) / amber (warning). Money semantics only.

### Buttons (`.btn`, `.btn--primary`, `.ask button`)
- default · hover (`translateY(-1px)`, brightness) · active (reset) · primary (metal-accent
  gradient + bevel). No verification colour on buttons.

### Card / answer (`.answer`, `.card`)
- default (metal-surface, bevel) · accent rail (`.answer` metal-accent border-image) · with
  verdict footer (`.answer__verdict` → shield + hash).

### Connection-health / staleness (WS7.7, tokens ready, component in WS7.7)
- fresh · "as of {date}" downgrade · disconnected. Uses amber/red (data health = money-adjacent),
  NOT the verify family — staleness is about the *inputs*, verification about the *recompute*.

### States every interactive component must define
default · hover · focus-visible (`--c-brand` ring) · active · disabled · loading (HTMX) ·
error · empty.

## 4 · Theme

Shell stays **Metallic Black** (dark). Verification tokens carry a
`@media (prefers-color-scheme: light)` companion (darker teal/indigo/violet) so shields stay
legible if a light surface renders them; the neutral shell is not otherwise re-themed here.
