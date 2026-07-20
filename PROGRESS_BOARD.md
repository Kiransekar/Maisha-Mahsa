# PROGRESS BOARD — checkbox mirror of MMX-1.0 (ORCH maintains)

Governing spec: `docs/MASTER_PLAN.md` (immutable). Detail log: `PROGRESS.md`.
`[x]` DONE · `[~]` WIP · `[c]` BLOCKED-CA · `[h]` BLOCKED-HUMAN · `[ ]` not started.

## Governance
- [x] GOV — spec at docs/ (444), tracking files, CODEOWNERS, CI guard

## P0 · Law & Trust
### WS1.A — Income-tax Act 2025 dual regime
- [x] WS1.A1 statutory_regime module (OPUS) — selector + form map + Tax Year; payment codes BLOCKED-CA
- [c] WS1.A2 citation re-point (SONNET) — BLOCKED-CA: needs 1961→2025 section map
- [c] WS1.A3 return artifacts (SONNET) — BLOCKED-CA: needs CA fixtures
### WS1.B — Labour Codes engine
- [x] WS1.B1 wage-definition engine (OPUS) — engine + PF/ESI/bonus wiring done, vector-locked
- [x] WS1.B2 hybrid gratuity (OPUS) — gratuity_hybrid + 3 vectors; boundary year-apportionment flagged for CA
- [x] WS1.B3 CTC validator (SONNET) — validator + rebalance suggester, never mutates; 8 tests
- [ ] WS1.B4 citation sweep (SONNET)
### WS1.C — Five proven defects
- [x] WS1.C1 194J 30k→50k
- [x] WS1.C2 194I per-month ₹50k
- [x] WS1.C3 ESI ceil-before-truncate + anti-pattern gate
- [x] WS1.C4 115BAA 25.168% + MAT excluded
- [x] WS1.C5 vault retention 8y from FY-end
### WS1.D — Missing sections & GST completeness
- [ ] WS1.D1 194Q/194T/TCS/206AA-AB
- [ ] WS1.D2 QRMP  · [ ] D3 CMP-08 · [ ] D4 IMS · [ ] D5 late-fee caps · [ ] D6 surcharge ladder · [ ] D7 e-way · [x] D8 MSME Form-1
### WS1.E — Oracle & rule packs
- [x] WS1.E1 oracle framework (seeded with defect vectors)
- [~] WS1.E2 expand to 300+ CA-initialled vectors (21 seeded: 7 WS1.C + 6 WS1.A + 4 WS1.B-wage + 4 WS1.B-wiring/gratuity, all ca_initials PENDING)
- [ ] WS1.E3 rule-pack versioning

## P0/P3 · WS2 state packs · WS3 Mahsa recomputation
- [ ] WS2.1–2.4
- [x] WS3.1 Rust recompute port (6 paths, parity harness; itr/regime/retention still Python-only)
- [~] WS3.2 parity gate (vector-parity live via tests/parity.rs; randomized Py↔Rust fuzz TODO)
- [x] WS3.3 kill default-healthy · [x] WS3.4 verdict object · [x] WS3.5 honest-state wiring (coverage json + tri-state badges)

## P1 · Platform (WS4 tenancy · WS5 RBAC · WS6 entitlements)
- [ ] WS4.1–4.8  · [ ] WS5.1–5.3  · [ ] WS6.1–6.4

## P2 · Product & UX (WS7 · WS8 · WS9)
- [ ] WS7.1–7.10 + WS7.V  · [ ] WS8.1–8.3  · [ ] WS9.1–9.2 · [x] WS9.3 draft-IRN honesty · [h] WS9.4 GSP (Human)

## P3/P4 · Hardening, GTM (WS10 · WS11)
- [ ] WS10.1–10.5  · [ ] WS11.1–11.3

## Standing quality gates
- [~] QG.1 statutory-oracle gate (framework live; expand vectors)
- [ ] QG.2 Playwright/Lighthouse · [~] QG.3 grep-gates (truncate-then-round live) · [ ] QG.4 weekly reconciliation
