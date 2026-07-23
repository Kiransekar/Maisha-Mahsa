# STATUTORY SOURCING — rescoping the oracle backlog

**Why this exists.** The launch checklist reads "Oracle 300+ CA-initialled vectors green", which
was being treated as one undifferentiated blocker requiring a chartered accountant for every value.
That is not what §0.6 says. It permits **either** (a) a CA-initialled vector **or**
(b) *"a cited primary source recorded in the vector file being created"*.

Most statutory values are published, unambiguous, and lookupable. Only a minority require
professional **interpretation**. This document splits the backlog on that line so the citable
majority can proceed now, and the expert review shrinks to a short, specific question list.

> **The audience question is settled and does not change this.** The product is for startup CFOs,
> not CAs. CA-as-*market* (testimonials, referral kit, Audit Room as a channel) is a distribution
> bet and is out of scope here. CA-as-*oracle* is a correctness requirement and is independent of
> who logs in — see §1.

---

## 1 · Why an external anchor is required at all

Mahsa proves **consistency, not correctness**.

The ✓ badge means "Rust independently recomputed what Python computed and matched to the paisa".
If both engines implement s.194J at a ₹30,000 threshold when the Finance Act says ₹50,000, they
agree exactly, the badge goes green, and the number is wrong. This is not hypothetical — it is
defect WS1.C1, found by audit, fixed 2026-07-20.

The recompute gate cannot catch this class of error by construction. The oracle vectors are the
**only** thing binding computation to law. Their provenance is therefore the load-bearing part —
not their count.

## 2 · The provenance problem in the current 33 vectors

Every existing vector carries `ca_initials: PENDING`, which is honest. But most carry
`source: "MMX-1.0 §WS1.A1"` — **our own spec document**. A spec is not a primary source; it is a
restatement whose own provenance is unrecorded. And the CI gate only asserts that *a* `source` key
exists, so citing ourselves passes it.

Two defects follow, both fixed by this document:
1. No way to distinguish "sourced from the Gazette" from "sourced from our own prose".
2. `ca_initials: PENDING` is applied uniformly, including to vectors that need **no** expert at all
   (structural rules, algorithm-derived cases), which inflates the expert backlog to ~10x its real size.

## 3 · The provenance taxonomy

Every vector declares exactly one `provenance` value. This replaces the blanket PENDING.

| Provenance | Meaning | Who unblocks it | Expert needed |
|---|---|---|---|
| `primary` | Value is published in a citable primary instrument: Finance Act / Income-tax Act section / CBDT circular or notification / CGST Act or rate notification / Gazette / EPFO-ESIC notification. `citation_url` + `citation_locator` (section, para, table row) required. | Agents, now | **No** |
| `derived` | Not a statutory value. A structural rule (regime boundary), an arithmetic consequence, or an algorithm-derived case with no external number. | Agents, now | **No** |
| `interpretation` | The statute is silent, ambiguous, or admits more than one defensible reading, and a *choice* had to be made. Must record the alternatives considered. | Expert review only | **Yes** |
| `unsourced` | Default. Nothing has been cited. **CI-blocking** — cannot ship. | — | — |

Rules:
- `primary` **must** carry a resolvable `citation_url` AND a `citation_locator`. A bare link to a
  homepage is `unsourced`.
- Citing `MMX-1.0` is **never** `primary`. The spec is a restatement, not an instrument.
- When in doubt between `primary` and `interpretation`, it is `interpretation`. Misclassifying an
  interpretation as primary is exactly the failure mode §0.6 exists to prevent.
- `interpretation` vectors ship **BLOCKED** and their figures render ◐, never ✓, until initialled.

## 4 · The split

### 4a · Tier A — `primary` (agents proceed immediately, no expert)

Published, lookupable values. This is the bulk of the 300.

- TDS/TCS rates and thresholds per section (194C/194I/194J/194Q/194T/206C, 206AA/206AB overlays)
- Income-tax slabs, surcharge and cess rates, both regimes; s.115BAA rate
- Interest and late-fee provisions: 234A/B/C, 234E, GST s.50 interest, GSTR-3B/1 late-fee and caps
- GST rates, RCM list, ITC set-off order, QRMP/PMT-06 mechanics, composition rates
- PF/EPS/ESI contribution rates, wage ceilings, admin charges
- Gratuity 15/26 formula and statutory ceiling; bonus 8⅓% (exactly 1/12) / 20% and eligibility limits
- Statutory due dates for every return and challan
- Form numbers under both the 1961 and 2025 regimes
- Vault retention periods (8y from FY-end)

### 4b · Tier B — `interpretation` (the actual expert backlog)

**This is the entire list. It is short.** Every item is already flagged BLOCKED-CA in `PROGRESS.md`
— none is new, and none is lookupable.

| # | Question | Ticket | Why it isn't lookupable |
|---|---|---|---|
| 1 | Year-apportionment convention for gratuity across the 2025-11-21 Code boundary — pre-boundary years on last-drawn Basic, post on s.2(y) base. Is per-year apportionment the right convention, or does the whole award follow the regime at exit? | WS1.B2 | The Code does not state a transition convention. We chose one and flagged it. |
| 2 | The percentage base for in-kind remuneration under Code on Wages s.2(y) — 15% *of what*? | WS1.B1 | s.2(y) caps in-kind at 15% but the base is not defined in the section. |
| 3 | The 1961 → 2025 **section** map (we hold only the FORM map: 16→130, 16A→131, 24Q→138, 3CD→26, 15G/H→121). | WS1.A2 | Spec enumerates forms only; a section-level concordance requires professional mapping. |
| 4 | Challan **payment codes** for the new forms (130/131/138). | WS1.A3 | Needs a filed sample or departmental confirmation; not published in a form we can cite. |
| 5 | Company base rate for the **non-115BAA** path (currently raises BLOCKED rather than guessing). | WS1.C4 | Depends on turnover-linked classification and applicable Finance Act year — a determination, not a constant. |
| 6 | Whether a specific payment falls under 194J vs 194C vs 194Q where the vendor's activity is mixed. | WS1.D1 | Classification is fact-specific and famously litigated. Likely a *product* question (ask the user to classify) rather than one we answer. |

**That is 6 questions, not 300.** Items 1–5 are a single focused review. Item 6 is arguably a UX
decision — let the CFO classify the vendor, and record their classification as the basis.

### 4c · Tier C — `derived` (no expert, no citation of law)

- The regime-boundary selector (earlier-of-credit-or-payment vs 2026-04-01) — a structural rule
- Rounding conventions already proven by Python↔Rust parity
- Arithmetic-consequence vectors (e.g. an ESI figure that follows once the rate is cited)
- The wage-base add-back algorithm cases, once the 15% base (item 2) is settled

## 5 · What changes in the build

1. Vectors gain a required `provenance` field; `unsourced` fails CI.
2. `primary` requires `citation_url` + `citation_locator`, and citing `MMX-1.0` as primary fails CI.
3. `ca_initials` stops being a blanket PENDING — it is required **only** on `interpretation`.
4. The launch checklist item is reinterpreted as: *every vector is `primary` or `derived` with a
   resolvable citation, and every `interpretation` vector is initialled.* The count matters far
   less than the provenance.

**Net effect on the schedule:** the "get a CA retained" blocker drops from the critical path for
the majority of WS1/WS2 and becomes a short, specific consultation on 5 questions. State packs
(WS2, 10 states × PT/LWF/S&E/min-wage) remain the largest genuine citation workload, but they are
Tier A — published state instruments, agent-citable, expert-spot-checked rather than expert-authored.
