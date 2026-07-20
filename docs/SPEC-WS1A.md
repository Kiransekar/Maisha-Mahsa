# SPEC-WS1A — Statutory regime module (MMX-1.0 §WS1.A1)

Design note for the dual-regime foundation. Handoff contract for §WS1.A2 (citation re-point) and
§WS1.A3 (return artifacts). Not the immutable spec — see `docs/MASTER_PLAN.md` for authority.

## Decision
The Income-tax Act 2025 applies to TDS/TCS events on or after **2026-04-01** (start of "Tax Year"
2026-27). The regime for an event is decided by the **earlier of its credit date and payment
date** — the same trigger the Act uses for deduction timing. All statutory presentation (section
citations, form names, period noun) is resolved *through* the regime; nothing downstream may
hardcode a 1961 form/section outside the frozen `regime_1961` namespace.

## Module: `api/app/core/statutory_regime.py` (pure, clock-free)
- `regime_for(credit_date=None, payment_date=None) -> "regime_1961" | "regime_2025"` — the core
  selector. `trigger_date()` = `min(credit, payment)`; `< 2026-04-01` → 1961 else 2025.
- `form_name(key, regime)` over the enumerated map (16→130, 16A→131, 24Q→138, 3CD→26,
  15G/H→121); unknown key raises (missing mapping is a hard failure, never a silent wrong form).
- `year_label(regime)` — "Assessment Year" (1961) vs "Tax Year" (2025).
- `payment_code_2025(nature)` — loader for the s.392–394 payment-code table (1001–1067). Ships
  **empty**: individual codes are statutory values and stay **BLOCKED-CA** until CA-sourced
  (§0.6). Callers must handle `None`, never guess.

## Done-when (met)
Boundary vectors resolve correctly — `credit Mar/pay Apr` and `advance-pay Mar/credit Apr` both →
1961; `both Apr`, `on-boundary` → 2025; form map locked both ways. Verify:
`pytest tests/statutory_oracle -k regime` (6 vectors, ca_initials PENDING).

## Handoff to A2 / A3
- **A2 (SONNET):** grep every hardcoded `"192"/"194x"/"Form 16"/"24Q"` outside `regime_1961` and
  route it through `form_name()` / a section map; add CI gate `scripts/check_no_stale_citations.sh`.
  Blocked on: the 1961→2025 **section** map (only the form map is enumerated in the spec today).
- **A3 (SONNET):** regenerate Form 138/130/131 + challan payment codes from CA fixtures in
  `tests/statutory_oracle/fixtures/` — BLOCKED until those fixtures exist (§0.6, §0.7).
