# Maisha-Mahsa — User Guide

Your self-hosted virtual CFO for an Indian startup. This guide takes you from a clean machine
to running the suite and using every feature. No prior knowledge of the codebase needed.

---

## 1. What this product is

Maisha-Mahsa keeps your company's books, taxes, payroll, GST, cap table, and compliance
calendar in one place — and **proves every number is correct** before showing it to you.

Two pieces work together:

- **Maisha** (Python) — the brain. Runs the web app, the twelve finance domains, and an
  optional local AI assistant that drafts explanations and answers questions.
- **Mahsa** (Rust) — the gatekeeper. A tiny, deterministic engine that *independently
  recomputes* every figure Maisha produces and checks it against CA-signed statutory rules
  (each rule cites its Act and section). If Mahsa and Maisha disagree, you see a flag, not a
  wrong number.

Everything you do is written to an **append-only, hash-chained audit log** — tamper-evident by
design. It runs entirely on your own machine; your financial data never leaves it (unless you
explicitly enable the cloud AI fallback).

**Who it's for:** a single founder/operator running one company. It is not multi-tenant.

---

## 2. Install & run

### Option A — Docker (easiest)

Brings up everything (app, gatekeeper, Redis, a mail catcher, and a local LLM) with one
command.

```bash
cd Maisha-Mahsa
make dev          # docker-compose up: api + dif + redis + mailhog + ollama
```

Then open **http://127.0.0.1:8000**. Outgoing emails are caught by MailHog at
**http://127.0.0.1:8025** (nothing is sent to real inboxes in dev).

### Option B — Local dev (two terminals)

You need `rustup`/`cargo` (for Mahsa) and Python 3.12 (for Maisha).

```bash
# Terminal 1 — Mahsa, the gatekeeper
cd dif && cargo run                 # serves http://127.0.0.1:8088

# Terminal 2 — Maisha, the app
make venv                           # creates api/.venv and installs everything
cd api && .venv/bin/uvicorn app.main:app --reload   # http://127.0.0.1:8000
```

Open **http://127.0.0.1:8000**.

### Health check

```bash
curl http://127.0.0.1:8000/health      # Maisha
curl http://127.0.0.1:8088/health      # Mahsa
```

Both should return OK. If Mahsa is down, Maisha will refuse to finalize numbers — that's the
safety design working, not a bug.

---

## 3. The web app — a tour

Open **http://127.0.0.1:8000**. The main pages:

| Page | URL | What it's for |
|---|---|---|
| **Home** | `/` | Dashboard: KPI strip, calendar, pending approvals, recent activity. |
| **Domain page** | `/d/<domain>` | The workspace for one finance area (e.g. `/d/gst`). See §4. |
| **Ask Maisha** | `/ask` | Ask plain-English questions about your finances; answers are fact-checked. |
| **CFO** | `/cfo` | Scenario planning, cap-table view, investor-update generator. |
| **Approvals** | `/approvals` | Anything requiring sign-off (e.g. ESOP pool change) queues here. |
| **Audit** | `/audit` | The hash-chained log of every decision, with trace viewer. |
| **Investor** | `/investor` | Preview and send quarterly investor updates. |
| **Parallel run** | `/parallel` | The 1-month go-live readiness gate (see §7). |

Every domain page has an **action bar**: buttons that open a form (`/d/<domain>/action/<key>/form`),
you fill it in, submit, and the result is recomputed by Mahsa and recorded in the audit log.

---

## 4. The twelve domains — what each does

Each domain is a workspace at `/d/<domain>`. Below is what you can do in each. (✅ = every
planned feature is built; the rest are mostly complete with a few items still on the roadmap —
see `BUILD_PROGRESS.md`.)

### Treasury — `/d/treasury` ✅
Your cash command centre. Import bank statements (HDFC, ICICI, Axis, or a canonical CSV),
get your consolidated cash position, **burn** and **runway**, see burn broken down by category,
get auto-sweep / FD-laddering suggestions, and reconcile UPI transactions and bank guarantees.

### GST — `/d/gst` ✅
Validate GSTINs, prepare **GSTR-1** (B2B/B2C/HSN) and download the JSON for the GSTN offline
utility (`/d/gst/gstr1.json`), compute **GSTR-3B** with correct ITC set-off order, reconcile
GSTR-2B with the Rule 36(4) ratio, compute late fee + interest, generate **e-Invoice IRNs** for
turnover > ₹5 Cr (`/d/gst/einvoice.json`), handle reverse charge, the composition scheme, LUT
for exports, and the **GSTR-9/9C** annual return.

### Ledger — `/d/ledger` ✅
Full double-entry accounting: chart of accounts (Indian GAAP), journal entries (balanced or
rejected), trial balance, **P&L**, **balance sheet**, depreciation (SLM/WDV, Schedule II),
account-wise general ledger, the cash-flow statement, and bank reconciliation. Entries from
payroll, GST, and revenue auto-post here.

### Revenue — `/d/revenue`
Customer master, GST-compliant invoicing (intra/inter-state), TDS on receivables, **AR aging**,
automated dunning reminders (T-7 through T+7) with email dispatch, credit notes, accrual/deferred
revenue recognition, and e-Invoice IRN + QR. Feeds outward supplies into GST automatically.

### Payroll — `/d/payroll`
Salary/CTC structures, **PF** and **ESI** with the correct ceilings, **TDS (s.192)** on the new
regime with rebate and marginal relief, the monthly payroll run, gratuity and statutory bonus
provisions. Download the **EPFO ECR** file (`/d/payroll/ecr.txt`), per-employee **payslips**
(`/d/payroll/<id>/payslip`) and **Form 16/16A** (`/d/payroll/<id>/form16`).

### Payables — `/d/payables`
Vendor master, the **TDS engine** (194C/194J/194H/194I with thresholds), PO↔GRN↔invoice 3-way
match, AP aging, **MSME 45-day** compliance (s.43B(h)), early-payment-discount capture, and an
ITC bridge into GST.

### Tax — `/d/tax`
Advance-tax schedule with s.234C interest, **TDS returns** (24Q/26Q/27Q) with s.234E late fee,
TDS aggregation from payroll and payables, the s.44AB tax-audit trigger, **MAT** (s.115JB),
s.234B interest, Form 26AS reconciliation, and s.80-IAC startup tax-holiday tracking.

### Equity — `/d/equity`
**Cap table** (founders/investors/ESOP/advisors with live ownership %), ESOP pool with a
board-approval gate, **SAFE** and convertible-note conversion, round dilution modelling, cap-table
snapshots, the quarterly investor-update generator, and dividend distribution (s.123).

### Forecast — `/d/forecast`
Annual budget + variance, rolling cash-flow projection with overdraft alerts, a **scenario engine**
(base/optimistic/pessimistic/hire), **burn multiple**, **unit economics** (CAC/LTV/payback),
headcount-driven payroll forecasting, and the quarterly re-forecast workflow.

### Expense — `/d/expense`
Claim → approval → reimbursement workflow, per-category policy limits, the petty-cash ₹10k
threshold, spend analytics, mileage/per-diem, and **receipt OCR**: upload a photo of a receipt
(`POST /d/expense/ocr-receipt`) and it extracts GSTIN, amount, and date.

### Vault — `/d/vault`
A tamper-evident document store: ingest files with SHA-256 hashing, automatic duplicate
detection, classification, retention policies (7y/3y/permanent), full-text search over OCR text
and tags, integrity verification, scan→OCR (`POST /d/vault/ocr-ingest`), and auto-archive when
retention expires.

### Compliance — `/d/compliance`
The **compliance calendar** across all statutes and forms, seeded with standard monthly
deadlines, with T-7/T-1/T-0 and overdue alerts, per-statute filing-status health, mark-as-filed
(with acknowledgement number), and MCA filings (AOC-4 / MGT-7 / DIR-3 KYC / DPT-3).

---

## 5. Ask Maisha & the CFO tools

- **Ask Maisha** (`/ask`) — type a question ("what's my runway?", "how much GST do I owe this
  month?"). Maisha drafts an answer, but **every number in it is checked against a deterministic
  computation** before you see it. If a figure can't be backed by a real fact, Maisha says so or
  routes it for approval rather than guessing.

- **CFO** (`/cfo`) — run financial scenarios (`/cfo/scenario`), review the cap table, and
  generate/send investor updates (`/cfo/investor/send`).

- **Investor** (`/investor`) — preview (`/investor/preview`) and send (`/investor/send`) a
  polished quarterly update built from your real numbers.

The local AI (Ollama) runs on your machine by default. The cloud fallback
(`claude-opus-4-8` / `claude-sonnet-4-6`) is **off** unless you explicitly enable it; even then,
inputs are PII-redacted and prompt-injection-filtered, and Mahsa still recomputes every number.

---

## 6. Trust: approvals & the audit log

- **Approvals** (`/approvals`) — actions with statutory or governance weight (e.g. changing the
  ESOP pool size) don't apply silently; they queue here for an explicit decision
  (`/approvals/<domain>/decide`), and the decision is sealed into the audit log.

- **Audit** (`/audit`) — every decision is an entry in an append-only chain where each entry's
  hash includes the previous entry's hash (`this_hash = sha256(prev_hash || entry)`). Change any
  past record and the chain breaks visibly. The trace viewer shows what Maisha proposed, what
  Mahsa recomputed, and which rule (with its Act + section) applied.

This is the core promise: you can hand the audit log to an auditor and prove what happened and
why, line by line.

---

## 7. Going live: the 1-month parallel run

Before you trust Maisha-Mahsa as your system of record, run it **alongside** your existing
process for a month. The `/parallel` page manages this:

1. **Start a run** (`/parallel/start`) — begins a 30-day window and captures a daily snapshot of
   all your metrics.
2. **Record observations** (`/parallel/observe`) — each day, log how the suite's numbers compared
   to your existing books.
3. **Cut-over gate** — readiness stays **HOLD** until enough clean daily observations accumulate,
   then flips to **GO** by a deterministic rule. No vibes; the data decides.

A daily snapshot can also be captured headlessly (`POST /history/capture`) for cron, and an 8pm
**CFO daily brief** can be scheduled (see `docs/PARALLEL_RUN.md` and the scheduler in `infra/`).

---

## 8. Exports you can hand to authorities / partners

| What | Where |
|---|---|
| GSTR-1 JSON (GSTN offline utility schema) | `/d/gst/gstr1.json` |
| e-Invoice IRN payload (NIC schema) | `/d/gst/einvoice.json` |
| EPFO ECR text file | `/d/payroll/ecr.txt` |
| Payslip (PDF) | `/d/payroll/<employee_id>/payslip` |
| Form 16 / 16A (PDF) | `/d/payroll/<employee_id>/form16` |

---

## 9. Troubleshooting

- **Numbers won't finalize / "gatekeeper unavailable".** Mahsa (`:8088`) isn't running. Start it
  (`cd dif && cargo run`) — Maisha intentionally refuses to show an unverified number.
- **AI answers are generic or absent.** The local LLM (Ollama) isn't running. With Docker,
  `make dev` starts it; locally, start Ollama or enable the cloud fallback. The rest of the app
  works fine without any LLM — only the drafting/Q&A assistance needs it.
- **No emails arrive.** In dev, mail goes to MailHog at http://127.0.0.1:8025, not real inboxes.
- **Is everything healthy?** `make verify` runs the full gate (Rust tests + Python tests +
  linters). Green means the build is sound.

---

## 10. Where to go next

- **What's built and what's left:** [`BUILD_PROGRESS.md`](./BUILD_PROGRESS.md)
- **The full product spec:** [`maisha_mahsa_v4_full_suite_prd.md`](./maisha_mahsa_v4_full_suite_prd.md)
- **Steps remaining before launch:** [`LAUNCH_READINESS.md`](./LAUNCH_READINESS.md)
- **The parallel-run mechanics:** [`docs/PARALLEL_RUN.md`](./docs/PARALLEL_RUN.md)
