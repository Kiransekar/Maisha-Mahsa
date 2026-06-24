# Maisha-Mahsa — Frontend PRD

> Product design for the web UI. Written as a PM spec: it defines *what* the frontend must do
> and *why*, with an implementation roadmap. Builds on the existing design tokens
> (`web/static/css/tokens.css`), the `skills/ui-polish` standard, and the no-build constraint
> (vanilla CSS + HTMX, per CLAUDE.md §7). Date: 2026-06-24.

---

## 1. Product thesis — what the frontend is *for*

Maisha-Mahsa is not "another finance dashboard." Its one differentiator is **trust you can
see**: every number is recomputed by a deterministic engine (Mahsa), every figure carries a
statutory citation, every decision is in a tamper-evident audit chain, and now an LLM (Maisha)
drafts answers that are *verified against the books before you ever see them*.

**The frontend's job is to make that guarantee tangible on every screen.** A generic dashboard
hides the machinery; ours must surface it — the green/amber/red verdict, the citation on each
figure, the "✓ verified by Mahsa" mark, the audit trail, and answers that come back
*verified-or-flagged*. If a founder can't *feel* the rigor, we've wasted the rigor.

Two user jobs:
1. **"Tell me if I'm okay."** At-a-glance health + what needs action today (the daily driver).
2. **"Do the thing."** Run payroll, file GSTR-3B, raise an invoice, approve a payment —
   operationally, in-app, with the gate enforcing correctness.

---

## 2. Current state & gap audit

| Area | Today | Gap |
|---|---|---|
| Navigation | Sidebar links are `/#domain` anchors on one page | **No real per-domain pages.** Dead nav. |
| Dashboard | Read-only KPI strip + health cards + calendar + approvals | No trends/charts; approvals have no Review action; no strategic prompt |
| Domain pages | None | 12 domains have full REST APIs, zero UI to use them |
| **Ask Maisha** | None | The whole LLM layer (claims, citations, verify, trace) is invisible |
| Actions | None | Can't create an invoice, run payroll, file a return, etc. |
| Approvals | Listed, not actionable | No review → approve/reject flow; nothing writes to audit |
| Audit & trace | None | The trust/observability story (audit chain, `llm_trace`) is unsurfaced |
| Interactivity | `dashboard.js` empty; HTMX loaded, unused | No partial updates, no forms, no drill-down |
| Settings | None | No LLM provider toggle, email config, etc. |

**Verdict:** the backend is ~complete (12 domains + harness, `make verify` green); the frontend
is a static scorecard. The project becomes "complete" when the UI can (a) show the verdict,
(b) answer questions via Maisha, and (c) drive every domain's actions through the gate.

---

## 3. Information architecture

```
Top bar:  [● Maisha-Mahsa]            [ Ask Maisha  ⌘K ]            [status: Mahsa ● | LLM ● | Settings ]
Left nav:
  Dashboard
  ── Money in/out ──   Treasury · Revenue · Payables · Expense
  ── People ──         Payroll
  ── Statutory ──      GST · Tax · Compliance
  ── Books ──          Ledger · Forecast
  ── Cap ──            Equity · Vault
  ── Command ──        CFO Strategy · Approvals · Audit
```

Page inventory (routes are real pages, not anchors):
- `/` Dashboard
- `/d/<domain>` Domain workspace (one reusable template, 12 instances)
- `/ask` Ask Maisha (also available everywhere as a ⌘K slide-over)
- `/cfo` CFO Strategy panel
- `/approvals` Approvals queue + review
- `/audit` Audit chain + LLM trace viewer
- `/settings` Configuration

---

## 4. Hero screens

### 4.1 Dashboard (`/`) — "Tell me if I'm okay"

```
Financial Command Center                                       Today, 24 Jun 2026
┌───────────────────────────────────────────────────────────────────────────┐
│ Cash ₹1.24Cr ▁▂▃▅  Burn ₹8.4L/mo ▇▅▃  Runway 14.8mo ▃▅▇  AR ₹45L  AP ₹12L │  ← KPI + sparkline
└───────────────────────────────────────────────────────────────────────────┘
DOMAIN HEALTH                                                  [ grid · clickable ]
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐   each card → /d/<domain>
│Treasury│ │ Payroll│ │  GST ⚠ │ │ Tax  ⛔ │   pill = green/amber/red verdict
│ 92 OK  │ │ 95 OK  │ │ 78 WARN│ │ 64 ALERT│
└────────┘ └────────┘ └────────┘ └────────┘
NEEDS ACTION TODAY                              COMPLIANCE (90-day)
┌─ Approvals (3) ──────────────┐               • 15 Jun Advance Tax Q1  OVERDUE
│ ⚠ Vendor AWS  ₹87K  [Review] │               • 18 Jun GSTR-3B May    in 3d
│ ⛔ CloudHost  ₹12K  [Review] │               • 20 Jun PF deposit     in 5d
│ ⚠ TDS Q1      ₹48K  [Review] │
└──────────────────────────────┘
STRATEGIC PROMPT (from CFO)
┌──────────────────────────────────────────────────────────────────────────┐
│ "Burn multiple improved to 1.4 — cleanest investor window in 2 quarters."  │
│                                       [ Draft Investor Update ]  [ Dismiss ]│
└──────────────────────────────────────────────────────────────────────────┘
Footer: Every figure here was recomputed & validated by Mahsa · audit-logged.
```

### 4.2 Ask Maisha — the differentiator (surfaces the whole harness)

A ⌘K command bar (slide-over everywhere) + a full `/ask` page with history. This is what makes
the product feel intelligent **and** trustworthy — it renders the P0/P1 pipeline directly.

```
Ask Maisha:  "What's our runway and is GST filing on time?"            [↵ Ask]
─────────────────────────────────────────────────────────────────────────────
Maisha · treasury + gst · drafted by ollama:qwen3:14b · 1.8s · ✓ verified by Mahsa
┌──────────────────────────────────────────────────────────────────────────┐
│ Runway is ~6.0 months (cash ₹1.20Cr, net burn ₹2.0L/mo). GSTR-3B for May  │
│ is 20 days overdue.                                                         │
│                                                                            │
│  Runway          6.0 months     ✓ recomputed                              │
│  Cash            ₹1,20,00,000   ✓ recomputed                              │
│  GSTR-3B late    20 days        ✓ recomputed   ⛔ GST-001                  │
│      └ CGST Act 2017 / Sec 47 — late fee accrues. [ File GSTR-3B → ]       │
│                                                                            │
│  Verdict: ⛔ RED · requires approval                          [ Review ]   │
└──────────────────────────────────────────────────────────────────────────┘
```
States the UI must render (all already produced by the backend):
- **✓ verified** — every number backed by a deterministic fact (`claim_verified`).
- **⚠ pending review** — the draft fell back / `requires_approval` (Golden Rule held: an
  unbacked number never shows as fact; it's flagged).
- **citations** as chips, linking to the triggering rule + a relevant action button.
- **provenance line**: domain(s), model label, latency, attempts — straight from `llm_trace`.
- **abstain** — "Not enough data to answer; connect an account / add the filing."

### 4.3 Domain workspace (`/d/<domain>`) — one template, 12 instances

```
GST                                                     Health 78 ⚠ WARN
┌─ KPI strip (domain-specific) ──────────────────────────────────────────────┐
│ Output tax ₹2.1L   ITC ₹1.4L   3B days late 20   Next due 20 Jul           │
└────────────────────────────────────────────────────────────────────────────┘
[ File GSTR-3B ]  [ File GSTR-1 ]  [ Reconcile ITC ]  [ Validate GSTIN ]   ← action bar
┌─ Triggered rules ──────────────────────────────────────────────────────────┐
│ ⛔ GST-001  GSTR-3B overdue · CGST Act 2017 / Sec 47        [ File now → ]  │
└────────────────────────────────────────────────────────────────────────────┘
┌─ Returns (table · sortable · HTMX paginate) ───────────────────────────────┐
│ Period   Type     Due        Filed      Status    Late fee                  │
│ 2026-05  GSTR-3B  20 Jun     —          OVERDUE   ₹1,000                     │
│ 2026-04  GSTR-3B  20 May     19 May     FILED     —                          │
└────────────────────────────────────────────────────────────────────────────┘
[ Trend chart: filing timeliness · ITC ratio ]
```
The template slots: domain KPI strip · action bar (quick actions open a **drawer form** that
POSTs to the existing `/api/<domain>/...` route) · triggered-rules panel · primary data table ·
trend chart. Each of the 12 domains supplies its KPI list, actions, table columns, and endpoints
via a small per-domain config — so we build the chrome once.

---

## 5. Component inventory (design-system additions)

All on the existing tokens, HTMX-driven, no build step. New components to add to `app.css`
(+ a small `components.css`), each documented in `skills/ui-polish`:

| Component | Use |
|---|---|
| Top bar + **command palette** (⌘K) | global Ask Maisha + status indicators |
| **Answer card** | Maisha response: narrative + figure rows + verified marks + citations + verdict |
| **Citation chip** | `RULE-ID · Statute / Section` → links to rule + action |
| **Verified badge** / **pending badge** | the trust mark on every figure |
| **Data table** | sortable, HTMX paginate, row-actions, empty/loading states |
| **Drawer** + **form controls** | quick actions (create/file/run) without leaving the page |
| **Status banner / pill** | the sacred green/amber/red (already tokenized) |
| **Sparkline** + **chart** | inline SVG sparklines (no dep); richer charts via uPlot over CDN (still no build) |
| **Toast/flash** | action results ("GSTR-3B filed · audit #a1b2…") |
| **Skeleton loader** / **empty state** | every async region degrades gracefully |
| **Audit row** / **trace row** | chain entry + LLM trace (model, attempts, verified, latency) |

---

## 6. Prioritized roadmap (what makes it "complete")

Sequenced by product value. Each ships behind `make verify` (add view/route tests + keep
the dashboard render test green).

- **F1 — Navigation + domain workspace shell.** Real `/d/<domain>` routes; the reusable domain
  template (KPI strip + triggered-rules + data table wired to existing GET APIs); fix the dead
  sidebar. *Turns a dead-end into a navigable app.*
- **F2 — Ask Maisha.** ⌘K command bar + `/ask`; render the answer card (verified marks,
  citations, verdict, provenance) from the `run_loop` outcome. *The differentiator; surfaces the
  entire harness.* **Highest value — recommend F1+F2 first as the spine.**
- **F3 — Action bar + forms.** Drawer forms POSTing to `/api/<domain>/...` (create invoice, run
  payroll, file GSTR-3B, post journal…). *Read-only → operational.*
- **F4 — Approvals flow.** `/approvals`: review a flagged claim (Mahsa verdict + citations) →
  approve/reject → writes an audit entry. *Closes the human-in-the-loop interrupt.*
- **F5 — CFO Strategy panel.** Scenario sliders → runway; investor-update generator (preview the
  existing email template → send); cap-table + dilution; 90-day calendar. *The "command" layer.*
- **F6 — Audit & trace viewer.** `/audit`: verify the hash chain in-browser; browse `llm_trace`
  (model/attempts/verified/latency). *Makes the trust story inspectable.*
- **F7 — Polish pass.** Skeletons, empty states, keyboard nav, ARIA, mobile/responsive,
  dark-mode QA (tokens already support it), 60fps. *The `ui-polish` bar.*

---

## 7. Technical approach (no-build, HTMX-first)

- **Server-rendered Jinja partials + HTMX** for all interactivity: table sort/paginate
  (`hx-get` → `<tbody>` swap), form submit (`hx-post` → row append + toast), approve
  (`hx-post` → row update), Ask Maisha (`hx-post /ask` → answer-card swap). No SPA.
- **Tiny JS only where HTMX can't reach**: command palette (⌘K) and drawer open/close — a few
  dozen lines, or `hyperscript` via CDN. Keep `dashboard.js` lean.
- **Charts without a build step**: hand-rolled inline SVG sparklines for KPI trends; for richer
  domain charts, uPlot via CDN (≈40 kB, no bundler). Data via a `/d/<domain>/series` JSON route.
- **Every figure carries provenance**: render the citation + verified mark from the claim/fold;
  never print a bare number the gate didn't bless.
- **Accessibility & performance**: semantic HTML, focus management on drawer/palette, prefers-
  color-scheme already wired, tabular-nums for money, skeletons to avoid layout shift.
- **Testing**: FastAPI `TestClient` route tests (each page 200s, renders key regions); keep the
  existing dashboard test; snapshot the answer-card states (verified / pending / abstain).

---

## 8. Definition of "complete"

The frontend is complete when a founder can, in-app and through the Mahsa gate:
1. See today's health and what needs action (Dashboard).
2. Ask any financial question and get a **verified-or-flagged** answer with citations (Ask Maisha).
3. Operate every domain — create/file/run/post (Domain workspaces + forms).
4. Review and approve/reject flagged items, writing the audit chain (Approvals).
5. Plan and communicate — scenarios, investor updates, cap table (CFO).
6. Inspect the trust — audit chain + LLM trace (Audit).

All ✅ under `make verify`, to the `skills/ui-polish` standard.
```
