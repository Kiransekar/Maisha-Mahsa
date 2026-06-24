# Parallel Run Runbook (PRD Layer 6)

> The final gate before relying on Maisha-Mahsa. Run it alongside your existing process
> (accountant / Tally / spreadsheets) for ~30 days and cut over only when every figure agrees.

## Why

Maisha-Mahsa is a zero-error financial product. Before it becomes the system of record, prove —
day by day, against your current source of truth — that its numbers match. The parallel run
turns "I think it's right" into a deterministic **GO / HOLD** decision.

## How it works

1. **Start the run** — open **Parallel Run** in the app and click *Start 30-day parallel run*
   (or `POST /parallel/start`). This records the window (start → +30 days).
2. **Capture daily** — the scheduler (`make scheduler` / the compose `scheduler` service) records
   Maisha's figures every day at 20:00 (`app.jobs capture`). You can also capture on demand from
   the CFO page.
3. **Record your figures** — each day, enter what your existing system reports for the key
   figures (e.g. `treasury / cash`, `revenue / annual_turnover_rupees`, `payables / ap_total`,
   `gst / gstr3b_days_late`). Values are in the **same unit as Maisha's metric — paise for money**.
4. **Reconcile** — the app shows, per observation: *Theirs* vs *Maisha* vs *Variance* vs ✓/⚠.
   A row is ✓ only when it agrees within tolerance (default: exact).
5. **Readiness** — the page shows agreement %, days observed, and a **GO / HOLD** verdict.
   **GO** requires *every* comparison to agree across the full window; otherwise **HOLD**:
   investigate each ⚠, fix the data or the rule, and keep observing.

## Daily ritual (≈2 min)

- Confirm last night's capture ran (Audit & Trace → LLM trace / the metric history).
- Enter today's figures from your existing system on the Parallel Run page.
- Scan the reconciliation table; any ⚠ is a discrepancy to resolve **today**, not at month-end.

## Reading discrepancies

- **Variance ≠ 0 on a money metric** → a real difference. Usually a timing/convention gap
  (e.g. a bill entered in one system not the other) or a genuine bug — chase it down.
- **"no capture"** → Maisha hasn't recorded that metric for that date; check the scheduler.

## Cut over

When the run shows **GO** for the full window, you can make Maisha-Mahsa the system of record.
Keep the audit log and the captured history — they are your evidence the cut-over was earned.
