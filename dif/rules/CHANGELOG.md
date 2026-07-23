# Rule-pack changelog

One entry per pack version, newest first. Every entry names what changed and the statutory
basis. The pack version is tenant-visible (Mahsa `/health` → app `/health` → UI banner), so
this file is the tenant-facing history of what the engine validates against.

## 2026.07.3 — 2026-07-23 (D1 bonus-rate wording)

- PAYROLL-004 description/action text: "8.33%" corrected to "8-1/3%" — CoW 2019 s.26(1)
  verbatim is "eight and one-third per cent." (= 1/12 exactly). Text-only; no thresholds,
  rates, or conditions changed (the rule's metric is the engine-computed `bonus_reserve`).
  Companion to the WS1.E2 D1 engine fix (bonus computed at the exact 1/12 fraction, not
  the 0.0833 approximation) and D2 (₹100 annual floor). Source: India Code aA2019-29.pdf,
  read verbatim (§0.6). Archived previous pack at archive/rules-2026.07.2.yaml.

## 2026.07.2 — 2026-07-23 (WS1.B4 citation sweep)

- PAYROLL-001 (PF deposit): statute re-pointed to Code on Social Security 2020 s.16(1)(a);
  EPF Scheme 1952 Para 38 retained as a saved instrument under s.164(2)(b)
  (ex EPF & MP Act 1952 s.6, repealed by CoSS s.164(1)).
- PAYROLL-002 (ESI deposit): Code on Social Security 2020 s.29; ESI regulations saved by
  s.164(2)(b) (ex ESI Act 1948 s.39-40).
- PAYROLL-003 (negative net pay): Code on Wages 2019 s.18 (ex Payment of Wages Act 1936 s.7,
  repealed by CoW s.69(1)).
- PAYROLL-004 (minimum bonus): Code on Wages 2019 s.26(1) (ex Payment of Bonus Act 1965 s.10,
  repealed by CoW s.69(1)).
- PAYROLL-005 action text: Code on Wages 2019 s.17 time limit (ex Payment of Wages Act 1936 s.5).
- No thresholds, rates, or conditions changed — citations only. Sources: India Code
  aA2019-29.pdf (CoW 2019) and aA2020-36.pdf (CoSS 2020), read verbatim (§0.6); the same
  instruments already cited by tests/statutory_oracle/vectors/ws1b_*.yaml.

## 2026.07.1 — seed set

- Initial CA-reviewable seed rules per PRD §4.4 across treasury/payroll/gst/tax and the other
  domains. Archived at archive/rules-2026.07.1.yaml.
