# WS7 UX Research — Painpoint Evidence Base

Grounds the WS7 UI/UX build (`MASTER_PLAN.md §9`) in real user pain from
financial / accounting / compliance SaaS. Every finding below was fetched and
verified against live source content; fabricated or unfetchable citations were
dropped during an adversarial pass. **81 verified findings** across 8 research
angles.

Evidence strength is marked honestly per finding: **[STRONG]** = highly-upvoted
thread or many independent voices · **[MOD]** = a few reports · **[ANEC]** = a
single voice. Indian-context sources are called out where relevant.

---

## 1 · Executive summary — cross-cutting themes, ranked

Ranked by evidence strength × frequency across the 8 angles.

| # | Theme | Strength | Why it matters for a trust-badged product |
|---|-------|----------|-------------------------------------------|
| T1 | **Numbers silently drift under you** — historical figures change, reports disagree, edits cascade into issued documents | STRONG | This is the exact failure our "independently recomputed and badged" promise exists to kill. It is also the #1 pre-existing fear of MSME owners with incumbent apps. |
| T2 | **Unannounced UI/layout churn breaks muscle memory** — menus move without warning, forced "Modern View" | STRONG (4 angles) | Finance users punish surprise relocations harder than any other UX class; layout stability is part of the trust contract. |
| T3 | **Reconciliation friction** — no bulk-accept, brittle exact-string matching, no confidence signal, flat undifferentiated lists | STRONG | Directly shapes the Exception Inbox and bank/GST matching flows. |
| T4 | **Bank-feed / connection staleness fails silently** — stale by a day, months missing, dedup on reconnect, undisclosed lookback windows | STRONG (5 angles) | A number recomputed against stale data is worse than no number; the badge must distinguish fresh from stale. |
| T5 | **Deadline-day portal collapse + no recovery path** — GST/MCA21 portals die on due dates; failed paid actions leave no self-serve fix | STRONG | Our tool sits adjacent to statutory deadlines; "portal down" ≠ "your filing is wrong" and users need attempt-evidence for penalty waivers. |
| T6 | **Opaque error / failure states** — bare "Something went wrong", no next action, no "is my money/filing safe?" | STRONG | The badge philosophy must extend into failure, not just success. |
| T7 | **Reporting is hard / non-customizable** — merge-field hell, "antiquated", basic non-customizable, unintuitive for non-finance users | STRONG (category-wide) | Report screens are where trust is read; drill-from-badge beats a report-builder skill. |
| T8 | **Onboarding demands training; migration gates/silently fails** — "take a class", paid-tier-gated migration, silent import stalls | MOD | The ≤15-min-to-first-verified-artifact target lives or dies here. |
| T9 | **Mobile ≠ web parity; low-end Android breaks** — divergent numbers across surfaces, blank ledger on flaky data, black screens | MOD | ₹10k-Android is the core device; a blank ledger reads as "my data is gone". |
| T10 | **Vernacular ≠ dictionary translation; WhatsApp is saturated** — literal Hindi rejected, Hinglish won; unsolicited WhatsApp = reflexive block | STRONG (WhatsApp) / MOD (Hinglish) | Shapes i18n (WS7.10) and the WhatsApp brief/alert channel (WS7.9). |
| T11 | **Field-level RBAC leaks** — "restricted" roles still expose cost/margin; adding a firm admin silently grants all-client access | MOD | Family/multi-partner MSMEs; a margin leak is trust-ending. |
| T12 | **Compliance surface is fragmented** — GST edge-cases (MDR, provisional ITC) not first-class; missing GSTR-2A/9/9C/GSTR-6/TDS forces leaving the tool | MOD–STRONG | A suite's calendar must cover ALL obligations, not just GST. |

---

## 2 · Themes in detail — pain, evidence, design decision

### T1 · Numbers silently drift under you  [STRONG]

**Pain.** Historical entries change after routine use; two screens legitimately
show different totals for "the same" concept and the user assumes a bug; an edit
to one document silently cascades into already-issued documents.

**Evidence.**
- Vyapar: "data disappeared and the calculations did not match" discovered at
  year-end reconciliation; a second 2+ yr user: "lost data...mismatching in the
  previous entries" — <https://www.capterra.com/p/180579/Vyapar/reviews/> [STRONG, India]
- myBillBook: "A billing software's core job is accurate calculations—if it
  can't compute correctly, it fails"; mobile vs web show different numbers for
  the same data — <https://www.capterra.com/p/202732/FloBooks/reviews/> [STRONG, India]
- QuickBooks Online: "if i change a date on an estimate sheet, that carries
  through to the invoices and if i dont catch it my clients get overdue
  invoices" (Kevin H.) — <https://www.capterra.com/p/190778/QuickBooks-Online/reviews/> [ANEC]
- Zoho Books: Customer Balances Summary vs Balance Sheet show different AR
  totals; Zoho maintains a standing KB page just to explain the gap —
  <https://www.zoho.com/us/books/kb/reports/mismatch-in-customer-balances-summary-and-balance-sheet-reports.html> [MOD]
- Zoho Books: trial balance dropped opening balances for BS items and assigned
  "opening balances" to P&L items (accounting-nonsensical) —
  <https://help.zoho.com/portal/en/community/topic/incorrect-trial-balance-reports> [ANEC]

**Design decision.** Every historical figure is append-only/immutable with a
visible audit trail; the Verified-Number Working panel (WS7.2) must let the user
drill any figure to its source transactions on demand. When two screens can
*legitimately* differ (GSTR-1 vs 3B liability, AR on invoice-list vs balance
sheet), surface an inline "why these differ" explainer **at the point of
comparison** — never let the user discover the gap and assume corruption. Any
edit that cascades into an issued/filed record must show "this will also change
N other records" before saving.

### T2 · Unannounced UI/layout churn  [STRONG — 4 angles]

**Pain.** Menus and features move without warning; forced default to "Modern
View" with no opt-back; core reports (Aging) silently restructured.

**Evidence.** All QuickBooks Online, <https://www.capterra.com/p/190778/QuickBooks-Online/reviews/>:
- "The constant changes to menus and layouts are frustrating. Features move
  without warning, which disrupts workflows" (Jennifer H.) [MOD]
- "You have to take a class to simple figure out how to do anything at all with
  this new system" (Terence J.) [MOD]
- "the part that I just don't appreciate, is the default to 'Modern View'"
  (Allison H., 5-star, still objected) [MOD]
- QBO Accountant: "The Aging Report format also changed...the new setup feels
  less convenient" (Jack R.) — <https://www.capterra.com/p/229996/QuickBooks-Online-Accountant/reviews/> [MOD]

**Design decision.** Once a screen's structure ships, freeze it. Any nav/IA
change is a **migration event**: opt-in preview period, an in-app "what moved"
changelog, and old paths kept reachable for a transition window — never a silent
default flip. Applies to our own domain-page/action-bar iteration cadence.

### T3 · Reconciliation friction  [STRONG]

**Pain.** Line-by-line manual approval even when the system's own suggested
match is correct (no bulk-accept); exact-string matching breaks on trivial
formatting differences; no per-match confidence; flat lists that don't rank by
₹/ITC impact.

**Evidence.**
- Xero: "Ability to select multiple/all transactions during reconciliation... to
  save users time from having to reconcile the transactions one by one" —
  **243 votes**, open since April 2022, still only "in development" Nov 2025 —
  <https://productideas.xero.com/forums/967136-banking-chart-of-accounts/suggestions/44988634-reconciliation-bulk-ok-for-reconciling-bank-tr> [STRONG]
- GSTR-2B: "INV-4587" vs "4587" (identical GSTIN/amount/tax) flagged as
  mismatch; a 1,200-invoice reconcile = 6–8 hrs manual VLOOKUP vs 10–20 min
  automated; flat list gives no way to see "which mismatches directly affect
  your ITC eligibility" — <https://www.aiaccountant.com/blog/automate-gst-2b-reconciliation> [MOD, India]
- QuickBooks Online: "the AI-matching for deposits and invoices being
  surprisingly flaky...it can't figure out which check goes to which invoice"
  (split payment) — <https://www.capterra.com/p/190778/QuickBooks-Online/reviews/> [MOD]

**Design decision.** Reconciliation/matching screens ship with bulk-select +
"accept all high-confidence matches" **from day one** (not v2), paired with a
visible confidence/match-source badge per line. Normalize identifiers before
comparing (strip prefixes, leading zeros, whitespace, case) — never brittle
exact-string. Rank surfaced discrepancies by rupee/ITC impact, not a flat list.
Low-confidence and split-payment cases get an assisted manual split UI, never a
silent best-guess.

### T4 · Bank-feed / connection staleness fails silently  [STRONG — 5 angles]

**Pain.** Transactions post a day late or go missing; whole months silently fail
to import; feeds drop and need silent re-auth; on reconnect old transactions get
re-imported as duplicates; undisclosed 90-day lookback windows cause balance
mismatches the user only learns of via a support article.

**Evidence.**
- Xero: "Bank integration does not work as advertised. Information comes
  truncated" (Adrien J.); "full months when I can't import" (Doran P.) —
  <https://www.capterra.com/p/120109/Xero/reviews/> [STRONG]
- Zoho Books: "Bank Feeds will drop from time to time, and re-authentication is
  necessary" (Ewan C.); posts "the day after the transaction has taken place,
  despite refreshing" (Luke T.) — <https://www.capterra.com/p/163115/Zoho-Books/reviews/> [MOD]
- Zoho Books: "retrieves only 90 days of transaction feeds...causing historical
  balance mismatches" — <https://www.zoho.com/us/books/kb/banking/opening-balance-offset.html> [MOD]
- Wave: sync "stopped working then started working again...resulted in some
  duplicate entries" (Kathryn S.) — <https://www.capterra.com/p/178021/Wave-Apps/reviews/> [ANEC]

**Design decision.** Every bank-fed account shows a persistent "last synced at
HH:MM" freshness indicator + manual "sync now" + a proactive **alert** (not
silence) when sync is stale beyond threshold. State any partial data window
explicitly next to the number ("as of last 90 days synced"). On reconnect after
an outage, run an explicit dedup/diff review step before auto-posting. The trust
badge downgrades to "verified against data that may be stale" when the feed is
gapped — this is WS7.7's core justification.

### T5 · Deadline-day portal collapse + no recovery path  [STRONG]

**Pain.** GST and MCA21 portals reliably degrade/crash on the exact deadline day
(login/OTP/captcha/save failures), and the penalty clock keeps running. When a
paid/committing action fails, the tool offers no self-serve recovery.

**Evidence.**
- GSTR-3B deadline: "slow loading", "delayed OTP delivery", "difficulty
  accessing key filing options"; CAs demanded fee waivers —
  <https://www.oneindia.com/india/gstr-3b-deadline-panic-gst-portal-glitches-disrupt-filing-here-s-what-happens-if-you-miss-it-8064911.html> [STRONG, India]
- MCA21 V3: "Validation Error: Submission Restricted", "DSC Verification
  Failed...despite correct digital signature", form details "masked during
  submission"; ICSI formally petitioned for extensions —
  <https://www.taxscan.in/top-stories/mca-v-portal-glitches-icsi-urges-mca-to-extend-filing-deadlines-waive-additional-fee-for-sept-dec-forms-1434949> [STRONG, India]
- ClearTax deadline slowdown: "During deadline times, the software is
  practically difficult to use due to heavy usage" (Pavan A.) —
  <https://www.softwaresuggest.com/cleartax-taxation/reviews> [MOD, India]
- ClearTax: "The ITR filing failed due to technical error but did not get the
  refund back or did not have any option to get my money back" —
  <https://www.consumercomplaints.in/bycompany/cleartax-a523353.html> [ANEC, India]
- GSTN backend: "server errors indicating the system is unable to fetch data
  from the backend application" — <https://www.businessupturn.com/finance/taxation/gst-portal-down-on-gstr-3b-deadline-day-chartered-accountants-demand-extension-as-filing-issues-persist/> [STRONG, India]

**Design decision.** Separate "ready to file" from "filed" so users can lock in
their recomputed liability **before** the portal opens (T-3 readiness state). On
submission failure, clearly distinguish "GST/MCA portal is down" from "your
filing has an error", log a timestamped attempt record the user can
export/screenshot as penalty-waiver evidence, and give a visible in-app
retry/refund path — never a silent background failure forcing a support ticket.
Surface a portal-status traffic-light near known spike dates (11th/13th/20th/25th).

### T6 · Opaque error / failure states  [STRONG]

**Pain.** Bare "Something went wrong" with no cause, no next action, no
indication whether money/filing state changed.

**Evidence.**
- HN: "it feels like the...company is just taunting me — 'I had a problem,
  loser, guess what it is!'"; thread consensus favors error IDs + context-
  specific messages — <https://news.ycombinator.com/item?id=41332589> [STRONG]
- Fintech UX: users need "Was the money deducted? Should I retry? Will I be
  charged twice?"; prescribed format answers what happened / what it means /
  what to do next / whether money is safe —
  <https://medium.com/pay10-design/designing-trust-in-fintech-why-ux-is-the-new-security-layer-164df67481a8> [MOD]

**Design decision.** Ban bare "Something went wrong" anywhere near a number or
filing action. Every failure state uses the **4-question template**: what
happened / what it means / what to do next / whether the underlying financial
state changed — with a traceable error ID tied into the audit log. The badge
extends into failure states, not just success. (Feeds WS7.3 alert grammar and
WS7.6 approval flow.)

### T7 · Reporting is hard / non-customizable  [STRONG — category-wide]

**Pain.** Report building is "difficult", "antiquated", basic and
non-customizable; invoice templates require editing raw merge fields in Word;
non-finance users can't parse what a report is showing.

**Evidence.**
- Sage Intacct: "I do not like the report writing. It is really difficult"
  (Kim P.); invoices need "the correct merge field...in Word documents"
  (Ilke H.) — <https://www.capterra.com/p/76/Intacct/reviews/> [STRONG]
- Xero: "The reporting features are very basic and there is no ability to really
  customize them" (Rishi G.) — <https://www.capterra.com/p/120109/Xero/reviews/> [MOD]
- QBO: "workflows aren't always as intuitive...especially for non-finance users"
  with perf issues on larger datasets (Khyan A.) —
  <https://www.capterra.com/p/190778/QuickBooks-Online/reviews/> [MOD]
- FreshBooks: "its reporting features feel limited" (verbatim-confirmed) —
  <https://www.capterra.com/p/142390/FreshBooks/reviews/> [ANEC]

**Design decision.** Let users drill from any summary trust-badge directly into
the underlying recomputation trail (line items → formula → source doc) instead
of learning a separate report-builder. Any report customization is a visual
builder (drag fields, live preview), never a merge-field/template-code workflow.
Report screens carry plain-language explanations of what's shown, and large
tables paginate/virtualize.

### T8 · Onboarding demands training; migration gates/silently fails  [MOD]

**Pain.** Base UI doesn't teach itself ("take a class"); migration help gated
behind a paid tier and stuck for months with a silently-failing wizard; bank
linking confusing at first; ~72% abandon onboarding with too many steps.

**Evidence.**
- QBO: "You have to take a class to simple figure out how to do anything" —
  <https://www.capterra.com/p/190778/QuickBooks-Online/reviews/> [MOD]
- Zoho Books: "They forced us to buy 12 months...saying migration won't be
  done unless we pay"; "This migration wizard fails for unknown reasons"
  (Shyamal P.) — <https://www.capterra.com/p/163115/Zoho-Books/reviews/?page=4> [ANEC]
- Zoho Books: "a bit tricky to understand how to link up my bank account"
  (Tracy O.) — <https://www.capterra.com/p/163115/Zoho-Books/reviews/> [ANEC]
- Onboarding stats: "72% of users abandon apps during onboarding if it requires
  too many steps"; avg SaaS activation ~37.5% —
  <https://www.shno.co/marketing-statistics/saas-onboarding-statistics> [MOD, directional]

**Design decision.** Never gate migration help behind a paid tier; never let an
import fail silently — show rows processed / rows rejected + why / retry-safe.
Core flows (raise invoice, record expense, check GST status) carry in-product
contextual guidance (tooltips, empty-state CTAs). Minimize required setup steps
before the user sees one real, badged number (one bank CSV or one Tally export)
rather than requiring full chart-of-accounts + tax + entity setup first.

### T9 · Mobile ≠ web parity; low-end Android breaks  [MOD]

**Pain.** Mobile and web diverge for the same ledger; app opens to a blank
ledger on flaky data; black-screen freezes; mobile app lags desktop.

**Evidence.**
- myBillBook: mobile/web "experience differ significantly"; desktop still beta —
  <https://www.softwareadvice.com/accounting/flobooks-profile/> [MOD, India]
- OkCredit: "every time I open this aap it shows empty" (iPhone 12 Pro) —
  <https://apps.apple.com/in/app/okcredit-udhar-bahi-khata/id1488748286> [ANEC, India]
- Khatabook: "black screen issues" (verified reviewer) —
  <https://www.capterra.in/software/197475/khatabook> [ANEC, India]
- FreshBooks: "The mobile app could use a little more work to be equivalent to
  the desktop version" (Rebecca R.) —
  <https://www.capterra.com/p/142390/FreshBooks/reviews/> [ANEC]

**Design decision.** Enforce single-source-of-truth so web and mobile can never
disagree on the same number (exactly what the recompute architecture must prove
across every surface). On flaky data, render last-cached ledger state first with
a retry affordance — never a blank screen. Budget crash/ANR/black-screen
telemetry + QA on Android Go / 2GB-class devices. Guarantee full read parity for
reports and trust badges on mobile.

### T10 · Vernacular ≠ dictionary translation; WhatsApp is saturated  [STRONG/MOD]

**Pain.** Literal formal-Hindi translation of finance terms was tested and
**rejected** as more confusing than English; WhatsApp is so saturated with
unsolicited business messages that users reflexively block senders and see
reporting as futile; a promoted "share invoice via WhatsApp" feature ships blank
PDFs.

**Evidence.**
- Khatabook: literal Hindi (Invoice → बीजक) rejected; built a merchant-tested
  Hinglish glossary; 30%+ run a non-English locale —
  <https://medium.com/@anoopjoyjoy/khatabook-app-to-superapp-f2b452255598> [MOD, India]
- WhatsApp spam: "businesses sending me unsolicited messages is a breach of my
  privacy"; one user blocked 15 business accounts in a month —
  <https://restofworld.org/2022/india-whatsapp-spam/> [STRONG, India]
- Vyapar: WhatsApp invoices "send blank files" (Siddharth K.) —
  <https://www.capterra.com/p/180579/Vyapar/reviews/> [ANEC, India]

**Design decision.** Ship transliteration-first Hinglish strings ("GST bharna
hai" register), NOT dictionary Hindi; statutory nouns stay English; pair every
badge/status with icon+color so meaning survives a non-reading user (WS7.10).
Any WhatsApp nudge is strictly opt-in, low-frequency, from a verified business
number, with per-alert-type mute — one unwanted message risks the whole channel.
Treat WhatsApp-share/export as a first-class, separately-tested critical path
(old WhatsApp builds, low-end webviews) with render-verification before send.

### T11 · Field-level RBAC leaks  [MOD]

**Pain.** A "restricted" role still exposes cost/margin data; adding a firm
admin silently grants full access to every linked client file.

**Evidence.**
- Vyapar: "Salesman" role still showed purchase prices/stock value/margins; "my
  two employees left my company...after seeing internal data" —
  <https://apps.apple.com/in/app/vyapar-billing-accounting/id6478382307?see-all=reviews&platform=iphone> [ANEC, India]
- Xero HQ: "suddenly notice 13 people that you don't recognise have full
  access...Administrators...automatically given full permissions over any linked
  client Xero files" —
  <https://productideas.xero.com/forums/967127-practice-tools/suggestions/47353781-user-access-administrators-hq-access-to-client-f> [MOD]

**Design decision.** Field-level RBAC verified per-screen, not menu-level —
audit every place a restricted role could indirectly see cost/margin (e.g. a
combined price+cost column). Client-to-CA access is per-file/per-role, and the
client sees an auditable "who can view these books" list.

### T12 · Fragmented compliance surface  [MOD–STRONG]

**Pain.** GST edge-cases (MDR exemption on sub-₹2,000 txns) aren't handled at
all, forcing manual entry; a "GST tool" lacks GSTR-2A reconciliation, Annual
Return 9/9C, GSTR-6, TDS/TCS — forcing users out of the tool for exactly the
work they bought it for; provisional/pending ITC has no distinct state.

**Evidence.**
- Zoho Books: "for transactions less than 2000 the MDR is not charged GST. There
  is no way to handle that" (Girish K.); support "just point to documentation" —
  <https://www.capterra.com/p/134507/Zoho-Books/reviews/> [MOD, India]
- ClearTax GST: "GSTR 2A reconciliation not supporting and Annual Return not
  supporting" (Sekar S.); rigid custom ERP template; "mismatch in filed data as
  per GST portal and report fetched from tool" —
  <https://www.capterra.com/p/265637/ClearTax-GST/reviews/> [STRONG, India]
- ClearTax: lacks "GSTR 6, credit register, and TDS and TCS returns" —
  <https://www.softwaresuggest.com/cleartax-taxation/reviews> [ANEC, India]
- Zoho: GSTR-2B/3B mismatch when vendor files late — bill "showing pending in
  GST portal for taking input tax credit" —
  <https://help.zoho.com/portal/en/community/topic/gst-2b-3b-mis-match> [ANEC, India]

**Design decision.** GST edge-cases (MDR thresholds, e-invoicing turnover
limits, reverse charge) are first-class built-ins, not "compute it yourself".
Import/mapping adapts to the shape of the user's own file (flexible column
mapping, not a rigid mandated template). Any recomputed report shows a live
diff against the authoritative portal figure rather than drifting silently.
GST reconciliation surfaces a third state — "pending on vendor's filing" — and
badges ITC as **provisional vs confirmed**, not binary match/no-match. The
compliance calendar spans ALL obligation types (GST, TDS, ROC, payroll), not
just GST.

---

## 3 · Mapping to WS7 tickets — validate / challenge

| Ticket | Verdict | Evidence |
|--------|---------|----------|
| **WS7.1** Design-system: verification family (teal/indigo + shield ✓/◐/✕) **separate** from money green/red | **VALIDATE** | T1/T4: the badge must express a *verification* state (fresh/stale/provisional) distinct from *money direction*; conflating them is exactly how trust products confuse users. Lakh/crore renderer is table-stakes for the Indian audience (T9/T10). |
| **WS7.2** Verified-Number chip + Working panel (inputs→formula→citations→docs→verdict hash→report-issue) + ◐→✓ lock-in | **VALIDATE (strongest)** | Directly answers T1 (silent drift, drill-to-source), T3 (per-match confidence), T7 (drill-from-badge beats report-builder). The "why these differ" explainer (Zoho AR mismatch) belongs here. |
| **WS7.3** Today view: cash strip · Needs-you queue · Trouble radar (alert grammar what/when/₹-consequence/one-tap) · penalties-avoided counter | **VALIDATE** | T6 4-question template and HN opaque-error evidence map onto alert grammar; the approval at-a-glance rollup (approval case study) supports a Needs-you queue. **Challenge:** ensure the penalties-avoided counter never itself becomes a fabricated/unverifiable number — it must be badge-backed. |
| **WS7.4** Five hubs, two altitudes, per-role default + remembered toggle; Altitude-2 keyboard-flow (Tally-speed) | **VALIDATE** | T-anti-Sage: avoid enterprise-ERP menu trees (Sage "only a Sage expert can use it"). Tally's keyboard-driven entry is a *most-loved* feature and a CA recommendation driver (<https://www.capterra.com/p/127762/Tally-ERP-9/reviews/> [STRONG]) — keyboard-flow at Altitude-2 is a hard adoption requirement, not a nice-to-have. |
| **WS7.5** Exception Inbox (Needs doc / categorization / Mahsa blocked / Awaiting approval / Feed broken; bulk ops with preview) | **VALIDATE (strongest)** | T3: Xero's 243-vote bulk-reconcile request open 3+ years is the single loudest signal in the corpus — bulk ops with preview is the fix. "Feed broken" state maps to T4; Wave dedup-on-reconnect needs the *preview* step. Rank by ₹/ITC impact (GSTR-2B flat-list pain). |
| **WS7.6** High-stakes approval flow (restated verified totals → typed/biometric confirm → audit receipt) | **VALIDATE** | Approval case study: users couldn't complete requests (info overload) and couldn't see status at a glance. **Challenge:** restated totals + typed confirm add friction — but WS7.V is explicit that *confidence, not speed*, is the metric, so this is correct. Add the T6 4-question failure state + T5 attempt-evidence receipt for failed commits. |
| **WS7.7** Connection-health strip + stale-data badge downgrade ("as of {date}") | **VALIDATE (strongest, 5-angle)** | T4 is the most frequent theme in the corpus. Every bank-fed number needs last-synced + stale alert + manual sync. Extend the concept: undisclosed data windows (Zoho 90-day) and GSTN lag also need "as of" disclosure. |
| **WS7.8** Onboarding ≤15 min (GSTIN prefill → bank CSV → Tally import → 5 Qs → first verified artifact) | **VALIDATE with CHALLENGE** | T8 supports minimizing steps-to-value and self-serve import with visible reject reasons. **Challenge:** GST + tax + bank setup is genuinely heavy; the ≤15-min target should mean *first badged number visible* (one CSV or Tally export processed), NOT full setup complete — front-load value before completeness. Tally import must handle real-file corpus (T1 stitching errors). |
| **WS7.9** Mobile PWA + ₹10k-Android budget + WhatsApp brief/alert with deep-link approvals (confirm in-app only) | **VALIDATE** | T9 (parity, low-end perf, blank-ledger) and T10 (WhatsApp saturation). "Confirm in-app only" is *correct and evidence-backed* — deep-link should never let a filing/payment commit from inside WhatsApp. **Challenge:** WhatsApp alerts must be strictly opt-in + verified-number + mutable per type, or the whole channel gets blocked (Rest of World [STRONG]). |
| **WS7.10** i18n day-one; English + Hinglish (transliteration-first; statutory nouns stay English); extraction lint | **VALIDATE (strongest for India)** | Khatabook's tested-and-rejected literal Hindi is direct proof: transliteration-first Hinglish is the right register, statutory nouns English. Pair every string with icon+color per T10. |

No ticket is contradicted by the evidence. The strongest independent
validation lands on **WS7.5 (Exception Inbox / bulk ops)**, **WS7.7
(connection-health)**, and **WS7.2 (Verified-Number Working panel)**.

---

## 4 · Anti-patterns to avoid — concrete competitor failures

1. **Silent retroactive number changes.** Vyapar/myBillBook. A wrong or changed
   historical total is the single most trust-destroying failure for a
   badge-everything product. → immutable history + drill-to-source.
2. **Silent UI relocation.** QuickBooks "Modern View" forced default, features
   move without warning, Aging report restructured. → migration-event treatment.
3. **Line-by-line reconcile with no bulk-accept.** Xero (243 votes, 3+ yrs). →
   bulk-accept + confidence badge from day one.
4. **Brittle exact-string matching.** GSTR-2B "INV-4587" vs "4587" false
   mismatch. → normalize before compare.
5. **Silent bank-feed staleness / dedup-on-reconnect.** Xero truncated months,
   Wave duplicates, Zoho 90-day undisclosed window. → freshness indicator +
   dedup preview.
6. **Bare "Something went wrong".** HN "taunting". → 4-question error template +
   traceable ID.
7. **Merge-field / Word-template report editing.** Sage Intacct. → visual builder.
8. **Paid-tier-gated, silently-failing migration.** Zoho (12-mo prepay,
   2-month stuck wizard). → free, transparent, retry-safe import.
9. **"Restricted" role that still leaks cost/margin.** Vyapar Salesman → 2 staff
   quit. → per-screen field-level RBAC.
10. **Dictionary-literal vernacular.** Khatabook rejected formal Hindi. →
    transliteration-first Hinglish.
11. **Unsolicited WhatsApp blast.** Rest of World: reflexive block. → strict
    opt-in, verified number, per-type mute.
12. **Silent transaction cascade into issued docs.** QBO estimate-date →
    customer overdue notice. → "changes N other records" confirm.
13. **Compliance work you must leave the tool to do.** ClearTax no GSTR-2A/9/9C;
    Zoho MDR "no way to handle". → first-class edge-case handling.
14. **Blank screen on flaky data.** OkCredit empty ledger reads as data loss. →
    last-cached + retry.

---

## 5 · Open questions for user validation (feeds WS7.V)

1. **Badge comprehension (WS7.V).** Do MSME owners read ✓/◐/✕ shield + teal/indigo
   as "verification state" and correctly *not* confuse ◐ (stale/provisional) with
   money-red? Run the badge comprehension test.
2. **Provisional ITC.** Does the third GST reconciliation state ("pending on
   vendor's filing") reduce the "is this credit claimable?" anxiety, or add
   confusion? Validate with CAs + owners (T12).
3. **≤15-min onboarding scope.** Is "first badged number from one bank CSV" a
   satisfying first-value moment, or do owners expect GST readiness before they
   trust it? Timed onboarding E2E + interview.
4. **Approval friction vs confidence.** Does restated-totals + typed confirm
   raise *confidence* without users abandoning to a workaround (approval case
   study risk)? A/B on confidence, not speed.
5. **Hinglish register.** Does "GST bharna hai" read as competent or unserious to
   a CA-adjacent user? Which statutory nouns must stay English? Weekly CA design
   hour.
6. **WhatsApp tolerance.** At what frequency/type does a Maisha alert cross from
   useful to block-worthy for this saturated audience? (Rest of World signal.)
7. **Keyboard-flow parity with Tally.** Can an Altitude-2 first-invoice beat
   4 min on low-end Android using keyboard-only entry (Tally-speed benchmark)?
8. **Connection-health legibility.** Does "as of {date}" + stale downgrade make
   users *trust* a stale number less without making them distrust the product?
9. **Failed-filing recovery.** On a simulated portal-down deadline, do users
   correctly distinguish "portal down" from "my filing is wrong" and find the
   attempt-evidence export? (T5.)

---

*81 verified findings · 8 angles · all source_urls fetched and content-checked;
fabricated/unfetchable citations dropped in adversarial pass. Strength marks are
honest per finding: STRONG / MOD / ANEC.*
