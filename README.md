# Maisha-Mahsa

The complete startup financial suite for the Indian regulatory context. A single-user,
open-source, self-hosted "virtual CFO": **Maisha** (Python/FastAPI) orchestrates and talks
to a local LLM, while **Mahsa** (a 12 MB Rust DIF sidecar) is the deterministic gatekeeper
that recomputes and validates every number against CA-signed rules before a human sees it.

> **New here? Read the [User Guide](./USER_GUIDE.md)** — install, run, and use every feature.
>
> **What** to build: [`maisha_mahsa_v4_full_suite_prd.md`](./maisha_mahsa_v4_full_suite_prd.md)
> **How** we build it: [`CLAUDE.md`](./CLAUDE.md) · **Where we are:** [`BUILD_PROGRESS.md`](./BUILD_PROGRESS.md)
> **What's left to launch (do this in order):** [`LAUNCH_READINESS.md`](./LAUNCH_READINESS.md)

## Layout

```
Maisha-Mahsa/
├── dif/        Mahsa — Rust DIF core (fold / validate / unfold). Pure, deterministic.
├── api/        Maisha — Python service: core, 12 domain modules, web UI, evals, tests.
├── infra/      docker-compose (api + dif + redis + mailhog + ollama), Caddy, env.
├── skills/     Project build skills — read the relevant one before a module.
└── Makefile    `make verify` is the gate.
```

## Quick start (local dev)

```bash
# 1. Mahsa (Rust) — needs rustup/cargo
cd dif && cargo test && cargo run        # serves http://127.0.0.1:8088

# 2. Maisha (Python)
make venv                                # creates api/.venv, installs api[dev]
cd api && .venv/bin/uvicorn app.main:app --reload   # http://127.0.0.1:8000

# 3. The gate (run before marking anything done)
make verify                              # rust tests + clippy + pytest + ruff + mypy
```

`make dev` brings up the whole stack in Docker (api, dif, redis, mailhog, ollama).
Full setup and usage walkthrough: **[USER_GUIDE.md](./USER_GUIDE.md)**.

## Status

Green and bottom-up verified — **57 Rust tests** (clippy-clean), **425 Python tests**, and
the **13/13 golden LLM eval** all pass. **100 of 116 domain features** are built across all
12 domains; **GST, Ledger, and Treasury are 100% complete**. See `BUILD_PROGRESS.md` for the
authoritative tracker.

## Features

Twelve domains, each a vertically-sliced module (math + rules + service + routes + UI), every
number recomputed by Mahsa before display. Boxes reflect the manifests in `api/app/domains/`.

### Treasury — cash command (8/8 ✅)
Multi-bank CSV import (HDFC/ICICI/Axis/canonical) · consolidated cash position · burn ·
runway · burn attribution by category · auto-sweep / FD-laddering suggestions ·
UPI reconciliation · bank-guarantee tracking.

### GST (11/11 ✅)
GSTIN format + check-digit validation · GSTR-1 (B2B/B2C/HSN) + JSON export · GSTR-3B with
statutory ITC set-off · late fee + s.50 interest · GSTR-2B reconciliation + Rule 36(4) ratio ·
HSN master + rate mapping · e-Invoice IRN (> ₹5 Cr) · reverse charge + self-invoice ·
GSTR-9/9C annual return · composition scheme · LUT for exports.

### Ledger (10/10 ✅)
Chart of accounts (Indian GAAP) · journal entries with double-entry validation ·
trial balance · P&L · balance sheet · depreciation (SLM/WDV, Schedule II) · general ledger ·
cash-flow statement (direct/indirect) · bank reconciliation · auto-posting from
payroll/GST/revenue.

### Revenue (10/11)
Customer master (PAN/GSTIN/TDS/terms) · GST-compliant invoicing (intra/inter-state) ·
TDS on receivables · AR aging · dunning schedule (T-7…T+7) + automated email dispatch ·
credit notes (s.34) · GSTR-1 bridge · accrual revenue recognition / deferred revenue ·
e-Invoice IRN + QR. ◻ export invoicing (LUT/IGST refund/FEMA).

### Payroll (10/13)
Salary/CTC structure · PF (₹15k ceiling) · ESI (₹21k ceiling) · TDS s.192 new-regime slabs
+ rebate + marginal relief · monthly payroll run · gratuity · statutory bonus (8.33%) ·
EPFO ECR text file · payslip PDF · Form 16/16A. ◻ Professional Tax · ◻ LWF · ◻ leave/attendance.

### Payables (7/9)
Vendor master (PAN/GSTIN/MSME/TDS section) · TDS engine (194C/194J/194H/194I) ·
PO↔GRN↔invoice 3-way match · AP aging · MSME 45-day compliance (s.43B(h)) · ITC bridge to GST ·
early-payment discount capture. ◻ recurring payables · ◻ payment run/disbursement.

### Tax (8/10)
Advance-tax schedule + s.234C interest · TDS returns (24Q/26Q/27Q) + s.234E late fee ·
TDS aggregation from payroll + payables · s.44AB tax-audit trigger · MAT (s.115JB) ·
s.234B interest · Form 26AS reconciliation · s.80-IAC holiday tracking. ◻ ITR-5/6 · ◻ transfer pricing.

### Equity (8/10)
Cap table (founder/investor/ESOP/advisor) · ESOP pool + board-approval gate ·
SAFE conversion (cap vs discount) · round dilution · cap-table snapshots ·
convertible notes (interest accrual) · quarterly investor-update generator ·
dividend distribution (s.123). ◻ share certificates/demat · ◻ rights issue/buyback.

### Forecast (7/8)
Annual budget + variance · rolling cash-flow projection + overdraft alert ·
scenario engine (base/optimistic/pessimistic/hire) · burn multiple · unit economics
(CAC/LTV/payback) · headcount → payroll forecast · quarterly re-forecast. ◻ rev-recognition timing.

### Expense (7/8)
Claim → approval → reimbursement workflow · per-category policy-limit check ·
petty-cash ₹10k threshold · category spend analytics · receipt parsing (GSTIN/amount/date) ·
photo → OCR (Tesseract) capture · mileage / per-diem. ◻ corporate-card reconciliation.

### Vault (8/9)
Ingest + SHA-256 hashing · duplicate detection · document classification ·
retention policy (7y/3y/permanent) · full-text search (OCR text + tags) ·
SHA-256 integrity verification · scan → OCR pipeline · auto-archive on retention expiry.
◻ RBAC access control.

### Compliance (6/9)
Compliance calendar (all statutes/forms) · seeded monthly statutory deadlines ·
T-7/T-1/T-0 + overdue alerts · per-statute filing-status health · mark-filed with
acknowledgement · MCA filings (AOC-4/MGT-7/DIR-3 KYC/DPT-3). ◻ secretarial · ◻ audit support · ◻ DPIIT.

### Cross-cutting
**Maisha LLM layer** (Ollama-first, Claude fallback, every claimed number fact-checked against a
deterministic source) · **hash-chained audit log** · **CFO daily brief + investor updates** ·
**1-month parallel-run** cut-over gate (`/parallel`) · **golden eval gate** (`make eval`).

## Non-negotiables

- **Mahsa is the gatekeeper.** Maisha never emits a final number Mahsa hasn't recomputed.
- **Exact money.** Integer paise everywhere internally; never a binary float in money math.
- **Zero error tolerance.** `make verify` must be green before a module is "done".
- **Auditable.** Every decision is sealed into an append-only, hash-chained audit log.
