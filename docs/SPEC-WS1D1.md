# SPEC-WS1D1 — Missing TDS/TCS sections (MMX-1.0 §WS1.D1)

Design note for 194Q, 194T, TCS s.394 (goods), and the 206AA/206AB higher-rate overlay. Not the
immutable spec — `docs/MASTER_PLAN.md` is authority. All new code lives in
`api/app/domains/payables/payables_calc.py` as **new** functions; the ported
`tds_on_payment` / `_TDS_SECTIONS` engine (194C/J/H/I) is untouched so Py↔Rust recompute parity
holds.

## Statutory-truth boundary (§0.6)
Only values MMX-1.0 §WS1.D1 states explicitly are inlined. Everything else is a parameter that
defaults to `None` and **raises when the rule fires** — never a silent zero/wrong deduction.

| Value | Source | Status |
|---|---|---|
| 194Q rate 0.1% | §WS1.D1 | inlined |
| 194Q / 206C(1H) threshold ₹50,00,000/vendor/FY | §WS1.D1 | inlined |
| 194Q → TCS 206C(1H) primacy | §WS1.D1 | inlined (rule) |
| 194T rate 10% | §WS1.D1 | inlined |
| 194T threshold ₹20,000 | §WS1.D1 | inlined |
| TCS s.394 **rate** | not in spec | **BLOCKED-CA** — required param |
| TCS s.394 **threshold** | not in spec | **BLOCKED-CA** — required param |
| 206AA no-PAN floor | not in spec | **BLOCKED-CA** — required param when fired |
| 206AB non-filer floor | not in spec | **BLOCKED-CA** — required param when fired |

## Functions

- `tds_194q(amount, *, aggregate_ytd=0)` — 0.1% on the purchase slice *above* ₹50L per vendor
  per FY. Excess mechanic: TDS falls only on the incremental portion of this payment that lands
  over the ₹50L running total (`_excess_over_threshold`). Result carries
  `tcs_206c_1h_suppressed` — **TDS primacy**: when 194Q bites, the seller's 206C(1H)/s.394
  collection is displaced.
- `tds_194t(amount, *, aggregate_ytd=0)` — 10% on partner remuneration/interest/commission once
  the FY aggregate *exceeds* ₹20,000; tax is on the full payment (not just the excess).
- `tcs_394_goods(amount, *, aggregate_ytd=0, rate=None, threshold=None)` — same excess mechanic
  as 194Q; **rate and threshold are BLOCKED-CA** and must be CA-sourced, else it raises.
- `apply_higher_rate(base_rate, pan_available, is_non_filer, *, no_pan_rate=None,
  non_filer_rate=None)` — 206AA/206AB overlay a caller applies on top of any base rate; **not**
  baked into `tds_on_payment`. Effective rate = highest of base and each triggered floor
  (no-PAN and non-filer can stack). Floors are BLOCKED-CA; a fired overlay with no floor raises.
  With PAN and a filer, `base_rate` passes through unchanged (no statutory number needed).

## Boundary semantics (strictly-above)
Both ₹50L and ₹20,000 are "exceeding" thresholds. At an aggregate of *exactly* the threshold the
excess is 0 (194Q/s.394) or the trigger is false (194T) — verified in the unit tests.

## Verify
`pytest tests/unit/payables && ruff check app tests && mypy app`. Domain unit tests assert the
spec-cited numbers (§WS1.D1 says "per-section vector files"; CA-initialled oracle vectors are
wired by ORCH later — these unit tests prove the values now).
