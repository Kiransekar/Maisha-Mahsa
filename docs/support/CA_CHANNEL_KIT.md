# WS11.2 — CA channel kit

Material for onboarding chartered-accountant firms as a channel (MASTER_PLAN §13 WS11.2,
§16 risk 5). Positioning is fixed: **the product eases the CFO's battles and makes the CA
look good — it never replaces the CA.** Statutory interpretation stays with the CA; the
product computes, cites and evidences.

---

## Part 1 — Audit Room walkthrough (demo script, ~15 minutes)

Run this on the seeded demo tenant (`make seed`) with a CA-role login.

1. **The seat** (1 min). CA seats are free and unlimited — invited from the client's
   Settings, never counted against the client's plan. The CA role is read-only: full Audit
   Room and queries, payroll visible as registers; no editing, no payment approvals.

2. **Badges = your audit trail, pre-built** (3 min). Open Today, tap a cash figure. The
   Working panel shows inputs → formula → rule citations → source documents → verdict hash.
   Explain the three states: ✓ (independently recomputed by the Rust engine, paisa-exact),
   ◐ (computed but not yet independently recomputed — honestly marked, never faked), and
   blocked (a mismatch that stops approval). Key line: *"a ✓ here is something you can rely
   on and trace; a ◐ tells you exactly where professional scrutiny still adds value."*

3. **Cell-level evidence** (2 min). From a bank-derived figure, open the cited source rows:
   "file, row N" excerpts resolved live against the content-addressed statement in the
   Vault. A changed or tampered source file visibly downgrades the badge — evidence cannot
   silently rot.

4. **The Audit Pack** (3 min). One click: trial balance, P&L, balance sheet, general
   ledger, statutory registers, 26AS reconciliation, MSME ageing — every figure badged and
   evidence-linked, with the audit-chain integrity certificate embedded. Sections that are
   not yet built (fixed-asset register) are declared, not padded.

5. **Query threads + sampling** (3 min). Raise a query pinned to a specific entry; the
   client responds with a document; resolution — all three events sealed onto the
   hash-chained audit log. The sampling helper pulls N random vouchers in a date range with
   their document bundles: vouching prep in seconds.

6. **Tamper-evidence** (2 min). Show `/audit/verify`: the client's whole chain re-verifies
   from its genesis. Every approval, memory update and query event is hash-linked — an
   edited record breaks the chain visibly.

7. **Close** (1 min). *"Your clients arrive at year-end with books whose numbers are
   pre-verified and pre-evidenced. Your hours shift from ticking to advising."*

## Part 2 — What the CA channel gets

- Free unlimited CA seats across all their clients, forever (product commitment, shipped).
- A referral mechanism: invites and sign-ups attributed to the referring firm
  (instrumentation shipped with WS8.3).
- The Audit Room as a working paper generator for their existing audit workflow.

## Part 3 — Referral terms (SKELETON — every bracket is an OWNER DECISION)

> **DRAFT — not an offer.** All commercial terms below are placeholders pending owner
> decisions and legal review. Do not share this section with CA firms until finalized.

1. **Referral fee**: [X]% of first-year subscription revenue for each referred client that
   remains a paying customer past [60/90] days, paid [quarterly].
2. **Attribution**: sign-ups via the firm's referral link or a recorded invite; window of
   [90] days from first touch; disputes resolved from the instrumentation log.
3. **Independence**: no fee is contingent on audit outcomes; a firm auditing a referred
   client must consider ICAI independence/Code of Ethics implications — [CA + counsel to
   confirm the compliant structure before launch; possibly restrict fees to non-audit
   clients].
4. **No exclusivity**, either direction.
5. **Term & exit**: either party may end participation with [30] days' notice; accrued
   fees survive.
6. **Branding**: firms may say they "work with" the product; no co-branding of statutory
   artifacts, ever.

Owner sign-off required on: fee %, payment cadence, attribution window, the
independence/ethics structure (item 3 — needs professional advice), and notice period.
