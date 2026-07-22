# WS7 BUILD CONTRACT — the blend

Neither research doc governs the UI alone. `WS7_UX_RESEARCH.md` says **what must never happen
to the user**; `BRAND_THEME.md` says **what it must look and sound like when we prevent it**.
This file is the join, and it is the checklist a WS7 component is reviewed against.

**Rule: no WS7 component ships until every row that applies to it is satisfied or explicitly
deferred with a reason in `PROGRESS.md`.** A component that is brand-correct but painpoint-blind
is not done — that failure already happened once (see §3).

---

## 1 · The contract

| Painpoint (UX research) | Brand expression (BRAND_THEME) | Component rule | Status |
|---|---|---|---|
| **T1** Numbers silently drift | Verification family (✓/◐/✕) never touches money green/red; "the verification chip is the logo" | Badge state comes from the server payload, never decided client-side. Unknown state falls to ✕, never ✓. | ✅ |
| **T7** Reporting opaque; drill-from-badge beats a report builder | Precision-as-decoration: lead with the exact number, then let it be interrogated | Every badged figure opens a **working panel**: inputs → formula → citations → documents → verdict hash → report-issue. A tooltip is NOT a working panel. | ✅ §3 |
| **T6** Bare "Something went wrong" | Flat declaratives; the ◐ state is an asset, not an apology | **4-question error template**: what happened · is my money/filing safe · what to do next · traceable ID. Applies to failure states too, not just success. | ✅ §3 |
| **T4** Feeds go stale silently | "State the mechanism, or state that it's pending" | Freshness is part of the badge, not separate from it: a figure computed on stale inputs **downgrades to ◐ with "as of {date}"**. Never a ✓ on stale data. | ✅ §3 |
| **T3** Reconcile line-by-line, no bulk | Zoho pattern: spacious shell, **dense interior** — working screens are Tally-dense | Bulk-accept exists from day one, and always **preview-then-confirm** (dry-run rows + ₹ impact before any mutation). | ⏳ server done, SPA pending |
| **T5** Portal collapse, no recovery path | Name the statute, don't say "compliance" | "Portal down" must be visually distinct from "your filing is wrong", and attempt-evidence must be exportable for penalty waivers. | ✅ P0-1 filing flow: receipts say "recorded as filed — keep your portal acknowledgement", `GET /api/filings/evidence` exports the sealed attempt bundle, and a refused record (400/403/409) is worded distinctly from a no-response failure. |
| **T2** Unannounced layout churn | Closed radius/spacing sets; hierarchy by size not weight | Layout is part of the trust contract. Relocations get migration-event treatment, never a silent move. | n/a (pre-launch) |
| **T9 / #14** Blank screen on flaky data | Borders-not-shadows; no decorative motion | Never render an empty shell on failure — show last-known data with its staleness, plus retry. A blank ledger reads as "my data is gone". | ✅ §3 |
| **T11** RBAC leaks cost/margin | — | Field-level, not screen-level. A "restricted" role must not leak margin. | ⏳ WS5.1 core done, not UI-wired |
| **T10** Dictionary-literal vernacular | Voice: flat declaratives, exact numbers, named statutes | English-only for now (i18n dropped per user). Statutory nouns stay English permanently. | ✅ scope |
| **T12** Fragmented compliance surface | Lakh/crore-native, name the form | The calendar covers every obligation, not just GST. Non-GST forms with no ported fee render ◐, never an invented ₹. | ✅ |

## 2 · Cross-cutting invariants

1. **Honest-empty ≠ zero.** An unwired source states that it is unwired. A genuine zero says so.
2. **Never invent a ₹.** Unknown impact renders "not yet known — we don't guess", never `₹0`.
3. **Money always grouped** `₹12,34,567`, always `tabular-nums`, one renderer per surface.
4. **Mono for statutory identifiers** — GSTIN/PAN/CIN/IRN/ARN/verdict hashes.
5. **One expressive motion in the entire product**: ◐→✓ lock-in. If decoration animates, a
   verification event stops meaning anything.
6. **Mahsa down is stated, not absorbed.** Explicit banner; no figure shown verified.

## 3 · Why this file exists

The first React pass (2026-07-21) was built from `BRAND_THEME.md` alone and shipped
brand-correct but painpoint-blind: the WS7.2 **working panel regressed to a `title` tooltip**
(T7) even though `/api/today` was already sending `inputs`/`formula`/`citations`/`verdict_hash`;
errors read "The API did not respond" (T6); and there was **no freshness signal at all** (T4) —
the single most dangerous gap, because a ✓ on stale inputs is precisely the trust failure the
badge exists to prevent. All four are fixed; the contract above is what caught them.
