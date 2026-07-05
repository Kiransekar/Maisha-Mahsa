# Maisha CFO — Agent Memory System (design)

> Goal: make Maisha a *real* AI CFO — one that knows **this** organization, remembers what it has
> done, and gets measurably better at **reducing tax** over time. Grounded in the Hermes four-layer
> memory schema, adapted to Maisha's two hard realities: the **Golden Rule** (Mahsa recomputes every
> number) and **per-organization** personalization.

## 0. The one principle we keep from Hermes

> *"Memory" is four jobs wearing one word. Match the storage to the job, and hard-cap what competes
> for the model's attention.*

Cramming durable facts, history, playbooks, and task state into one vector store is the mistake most
memory systems make. We split them, exactly as Hermes does — **but we add a fifth, cross-cutting law
that Hermes doesn't need:**

> **The Golden-Rule memory law:** memory may store *facts about the org, preferences, decisions,
> playbooks, and statutory citations*. It may **never** store a computed rupee figure that the LLM
> then repeats as truth. Every number is recomputed by Mahsa / the deterministic calc engines at
> inference time. Memory holds *formulas and thresholds*, never *answers*.

A memory system that lets the agent "remember" last year's ₹12,40,000 tax and state it would destroy
the product's entire trust thesis. So money lives in the domain tables (recomputed on demand);
memory holds only what is durably *true* or *learned*.

## 1. The four layers, mapped onto Maisha

| Layer | Hermes | Maisha realization | Store | Lifecycle |
|---|---|---|---|---|
| **Semantic** — what is true, durably | `USER.md`, `MEMORY.md`, hard-capped, always in prompt | **CFO Profile** per org: who the org is + learned CFO posture/preferences | `org_memory` table (char-capped) | rarely changes; foreground + daemon writes |
| **Episodic** — what happened, when | SQLite + FTS5, unbounded, retrieved on demand | **Decision history** — *we already have it*: the hash-chained `audit_log`. Add search. | `audit_log` + a search index | append-only, never mutated |
| **Procedural** — how to do a task | Skills, progressive disclosure | **Tax-optimization playbooks** (the differentiator) | `playbook` table, index-in-prompt/body-on-demand | shipped catalog + org-learned |
| **Task state** — what am I doing now | the context window, no persistence | the drafting loop's context | — | expires with the turn (by design) |

Everything is keyed by `company_id` (a strict isolation boundary — one org must never read
another's memory, same lesson as the tenant-cache class of bug). Today there is one company per
deployment, so `company_id` defaults to it; the schema is ready for true multi-tenant with no rework.

---

## 2. Semantic layer — the CFO Profile (personalization)

Two hard-capped blocks per org, injected into the drafting system prompt every turn (snapshotted at
session start so the prompt prefix never shifts mid-session — Hermes' rule):

- **`ORG`** (≈1400 chars) — *who the org is.* Mostly **derived** from the `company` row (PAN, GSTIN,
  sector, incorporation date, MSME/DPIIT status, FY end, state) so it's never stale, plus a few CFO
  facts that aren't in the schema: entity type (Pvt Ltd / LLP / OPC), turnover band, employee count
  band, export status, group structure.
- **`CFO_MEMORY`** (≈2200 chars) — *the agent's learned posture.* Standing preferences and lessons:
  - **tax regime choices** ("company on new regime 115BAA; directors on old regime"),
  - **standing instructions** ("always maximize ITC before cash payment"; "defer discretionary capex
    to Q4 for depreciation timing"),
  - **risk appetite** ("conservative — no aggressive positions without CA sign-off"),
  - **corrections** the operator made ("we are 44ADA-eligible, not 44AD"),
  - **known constraints** ("auditor requires board approval for any 80-IAC claim").

**Hard caps are a feature, not a limit** (Hermes' argument): they force *durable facts only*. On
overflow the write is **rejected** and the agent must consolidate (drop/shorten), so the hot layer
never degrades into a dumping ground. Caps are in **characters** (model-agnostic).

## 3. Episodic layer — decision history we already have

The `audit_log` is *already* an append-only, hash-chained episodic memory of every fold/decision.
It has been write-only; we add **retrieval**:

- **Search index, DB-agnostic** behind a `MemorySearch` port:
  - **SQLite (dev/tests):** FTS5 virtual table + insert/update/delete triggers (exactly Hermes'
    self-maintaining index), BM25 ranking.
  - **Postgres (prod):** a `tsvector` GIN column maintained by trigger, `ts_rank` ranking.
- **Retrieval shape** (Hermes' "bookends"): a hit returns a *shaped window* — the session's opening
  decision, a tight window around the match, and the resolution — not one orphan row and not the
  whole history. Org-scoped, deduped by lineage.
- **What it buys the CFO agent:** recall. *"Did we defer this expense last year?"*, *"what did the
  auditor flag on ITC in FY24?"*, *"when did we last file GSTR-3B late?"* — answered from real,
  hash-verified history, never invented.

Because it's the audit chain, episodic recall is **tamper-evident by construction**: a memory the
agent surfaces can be proven to have actually happened.

## 4. Procedural layer — the Tax-Optimization Playbook library (the differentiator)

This is where "AI CFO" earns its name. A **playbook** is a structured skill:

```
id, company_id (null = universal/shipped)
name                "Maximize Section 80C / 80CCD(1B) headroom"
trigger             one-line relevance hint (lives in the prompt index)
applies_when        machine-checkable predicate over FACTS (e.g. entity_type='individual')
statute, section    citation (Mahsa-grade; no advice without a cite)
steps               the playbook body (loaded on demand — progressive disclosure)
headroom_formula    a DETERMINISTIC expression the engine evaluates (never the LLM):
                    e.g. max(0, 150000_00 - current_80c_invested_paise)
risk                low | medium | aggressive
```

**Progressive disclosure** (Hermes): only `name` + `trigger` sit in the prompt (50 playbooks = 50
index lines, not 50 bodies). The agent scans the index, opens the one that fits, pulls the body.

**Golden-Rule compliance:** the playbook proposes a *strategy* and a *formula*; the engine computes
the ₹ headroom deterministically and Mahsa validates it. The LLM narrates and cites — it never emits
the number. So "you can still invest ₹47,000 under 80C to save ₹14,100 in tax" is a **computed,
audited** figure wearing a playbook's explanation.

**The shipped catalog** (universal, ~20–30 playbooks — the CFO's known toolkit):

- **Direct tax:** 80C/80D/80CCD(1B) headroom · old-vs-new regime choice per person · 115BAA/115BAB
  company rate election · additional depreciation u/s 32(1)(iia) & capex timing · 80-IAC startup
  holiday (DPIIT) · 44AD/44ADA presumptive eligibility · R&D 35(2AB) · MAT/AMT credit use ·
  carry-forward loss set-off ordering · capital-vs-revenue expenditure classification · director
  remuneration: salary vs dividend · leave-encashment/gratuity timing · TDS §197 lower-deduction
  certificate · advance-tax scheduling to avoid 234B/234C.
- **Indirect tax (GST):** ITC set-off order optimization (Rule 88A) · LUT for zero-rated exports
  (avoid blocked capital) · RCM planning · ITC reconciliation before cash payment · e-invoice/2B
  matching to protect ITC.
- **Structural:** MSME 45-day discipline (cash-flow, not tax, but CFO-core) · inter-company pricing
  hygiene · dividend vs buyback.

Each ships with statute + section, an `applies_when` predicate, and a deterministic `headroom_formula`
so the "how much can we save" number is always real.

**Org-learned playbooks:** the daemon promotes a playbook to org-specific when the org repeatedly
adopts (or repeatedly rejects) a strategy, or the operator says "always do X."

### The Tax Optimizer (what ties it together)

A `TaxOptimizerService` that, per org and period:
1. builds the org's deterministic FACTS (existing snapshot machinery),
2. filters the playbook catalog by `applies_when`,
3. evaluates each `headroom_formula` **deterministically** → ₹ impact,
4. ranks by `impact × feasibility ÷ risk` and the org's risk appetite (from the CFO Profile),
5. returns a prioritized, **cited**, **Mahsa-validated** action list — and seals it to the audit chain.

Personalized (regime, prior claims, appetite) and **cumulative** (it remembers what was adopted or
declined, and why, so it stops re-suggesting rejected moves). *That* is a CFO that gets better.

## 5. Task state — no persistence

Lives in the drafting loop's context and expires with the turn. Keeping it would be a bug. (Hermes.)

## 6. Consolidation — the memory daemon

Learning must never cost the operator latency, and must never corrupt the turn it learns from
(Hermes). Two clocks:

- **Foreground `memory` tool** — the agent writes an obviously-durable fact mid-session (respecting
  the char cap; overflow ⇒ forced consolidation).
- **Background review** — after the response is delivered, a **sandboxed** reviewer (whitelisted to
  *only* the memory/playbook tools, best-effort, isolated so its prompts never leak into real
  history) replays the turn and asks "was anything here worth keeping?" It fires on Hermes' signals:
  **user corrections, repeated flags, a strategy that worked, "remember this."** We ride the existing
  scheduler for a nightly consolidation pass in addition to per-session review.

Writes are serialized (the DB is the lock; the audit chain's append mutex already exists) so
concurrent sessions can't lose updates.

## 7. Storage summary (all on the existing TypeORM stack — no new infra)

```
org_memory   (company_id, kind[org|cfo], content, char_used)          -- semantic, hard-capped
playbook     (company_id?, name, trigger, applies_when, statute,      -- procedural
              section, steps, headroom_formula, risk, adopted_count, rejected_count)
audit_log    (+ FTS5/tsvector index + triggers)                       -- episodic (already exists)
memory_event (company_id, ts, kind, ref)                              -- daemon signal log (auditable)
```

No vector DB, no embedding model, no second service — a few tables and a search index, exactly the
Hermes thesis: the sophistication is in the **boundaries**, not the infrastructure. (Semantic/vector
retrieval is a later, optional bolt-on behind the `MemorySearch` port if lexical proves insufficient.)

## 8. Phased build

- **P1 — Semantic + isolation:** `org_memory` table + char-capped `MemoryService` (reject-on-overflow)
  + inject the CFO Profile into the drafting prompt (snapshot at session start). Company-derived ORG
  block. *Immediately makes the agent personalized.*
- **P2 — Tax Optimizer + shipped playbooks:** `playbook` table + ~20 universal playbooks with
  `applies_when` + `headroom_formula`; `TaxOptimizerService` (deterministic headroom, Mahsa-validated,
  ranked, cited); surface on a `/optimize` route + a Tax page in the UI. *The killer feature.*
- **P3 — Episodic retrieval:** FTS5/tsvector index over `audit_log` + `MemorySearch` port + bookends
  + a `recall` tool the agent can call. *Gives the agent real recall.*
- **P4 — Consolidation daemon:** background post-session review (sandboxed, best-effort) + nightly
  pass on the scheduler; learn org-specific playbooks and CFO-profile facts from adopted/rejected
  strategies and corrections. *Makes it get better over time.*

Each phase is independently valuable and gated (build + tests) like every prior slice.
