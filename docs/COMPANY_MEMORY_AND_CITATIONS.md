# COMPANY MEMORY & CELL-LEVEL CITATION ANCHORS — Implementation Design

**Doc ID:** SPEC-MEMCITE-1.0 · **Date:** 2026-07-23 · **Status:** design, ready to build
**Governance:** subordinate to `docs/MASTER_PLAN.md` (MMX-1.0, immutable). Every ticket below
obeys §0.4 (Prime Directive), §0.5 (verify in CI), §0.6 (statutory truth), §0.8 (security floor).
Log all work to `PROGRESS.md` only. This doc derives from two verified research passes
(research:company-memory, research:cell-citation); all `file:line` cites were checked against
the tree, all web claims against fetched sources.

---

# PART A — PER-COMPANY MEMORY LAYER (main FastAPI `api/`)

## A0. Thesis

The api-nest memory system (commits `9502175` P1+P2, `1aaac58` P3, `c0b075f` P4) is a complete,
survey-grounded, deterministic per-org memory layer. Its **schema and mechanisms port**; its
**org resolution and query scoping do not** — they are single-tenant and must be rebuilt on the
main product's existing Principal/RLS plumbing (`api/app/core/principal.py`,
`api/alembic/versions/0002_multitenant_core.py`). No vector DB, no embeddings, no new
dependency, no new infra: plain org-scoped tables plus the audit log we already have.

Survey grounding (arXiv:2512.13564v2, *A Survey on Memory for LLM Agents*): §5.2.2 endorses
soft/temporal updating over destructive replacement (Zep-style "marking conflicting facts with
invalid timestamps rather than deleting them") plus offline consolidation ("eventual
consistency paradigm") — exactly Maisha's archive-on-supersede + nightly evolve. §5.3.3
endorses lexical TF-IDF/BM25 "in precision-oriented retrieval scenarios" — validating
lexical-first recall for exact statutory terms/GSTINs. §7.7 requires "explicit mechanisms for
access control, verifiable forgetting, and auditable updates" — Maisha's audit-sealed,
versioned, org-segmented design is precisely this, and **no surveyed commercial system
(Zep/Letta/mem0/LangMem) seals memory writes into a tamper-evident chain. We already do**
(api-nest `memory.service.ts:76-95`). That is the differentiator; keep it.

## A1. Memory types (all four proven in api-nest; nothing else)

| # | Type | Storage | Justification |
|---|------|---------|---------------|
| 1 | **Org profile facts** | none — rendered live from the org/entity rows (api-nest `renderOrg`, `memory.service.ts:139-151`) | Letta/MemGPT "memory block" pattern: small labeled always-in-context blocks under a size budget (letta.com/blog/memory-blocks). Derived live ⇒ never stale. Needs **no retrieval at all**. |
| 2 | **CFO posture block** (preferences/corrections: regime choices, standing instructions, risk appetite) | `org_memory` table, hard cap 2200 chars, explicit-write only | api-nest `CFO_CHAR_LIMIT=2200` with reject-on-overflow (`memory.service.ts:21,66-73`); cap doubles as importance-based forgetting pressure (survey §5.2.3). |
| 3 | **Episodic decisions** | already exists: the hash-chained `audit_log` IS the episodic store | Tamper-evident by construction; recall returns decision+hash, never a number-as-truth (api-nest `AGENT_MEMORY_DESIGN.md:63-79`). Zero new tables. |
| 4 | **Playbook outcomes** (adopt/dismiss feedback) | `playbook_feedback` table | Verified live in api-nest: dismissing GST-LATEFEE dropped the quantified total ₹800→₹0 (`c0b075f`); demotes dismissed moves and zeroes their claimed savings (`playbook-feedback.entities.ts:8-16`, `tax-optimizer.service.ts:64-83`). |

**Deferred with named triggers** (do NOT build now): embeddings/semantic retrieval — trigger:
lexical recall measurably misses paraphrase queries in real usage AND the LLM-off product mode
is preserved (recall must keep working with the LLM off; lexical SQL does, an embedding
pipeline does not). Temporal knowledge graphs (Zep, arXiv:2501.13956: Graphiti, 94.8% DMR) and
extraction pipelines (Mem0, arXiv:2504.19413: 91% p95 latency reduction) solve the
**long-conversation** memory problem Maisha does not have — our episodic unit is a single
sealed decision, not a 200-message session.

## A2. Schema (migration `0011_org_memory`)

Three tables, all keyed on `org_id uuid NOT NULL` (matching `orgs.id`; fixes api-nest defect
(c): `company_id` integer-default-1 at `org-memory.entities.ts:12`). **RLS policies ship in the
same migration or CI fails** (MASTER_PLAN §0.8, WS4.1) — copy the exact pattern from
`0002_multitenant_core.py:123-136`: `ENABLE ROW LEVEL SECURITY` + policy
`USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org())`.

```sql
CREATE TABLE org_memory (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id),
  kind        text NOT NULL DEFAULT 'cfo_posture',      -- one kind today; text not enum
  content     text NOT NULL CHECK (char_length(content) <= 2200),  -- DB-enforced cap, §0.8 spirit
  updated_at  timestamptz NOT NULL DEFAULT now(),
  updated_by  text NOT NULL,                            -- Principal.user_id
  UNIQUE (org_id, kind)
);
CREATE TABLE org_memory_history (                        -- soft/temporal updates, never overwrite
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES orgs(id),
  kind          text NOT NULL,
  content       text NOT NULL,
  superseded_at timestamptz NOT NULL DEFAULT now(),
  superseded_by text NOT NULL,
  audit_seq     bigint                                   -- row id of the sealed memory.update event
);
CREATE TABLE playbook_feedback (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES orgs(id),
  playbook_id text NOT NULL,
  verdict     text NOT NULL CHECK (verdict IN ('adopted','dismissed')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  created_by  text NOT NULL,
  UNIQUE (org_id, playbook_id)                           -- latest verdict wins via upsert
);
-- + RLS on all three, same migration file.
```

SQLAlchemy models in `api/app/db/models/` follow the `legal.py` precedent (`org_id` mapped
column commented as tenant boundary, `legal.py:36`).

## A3. Org resolution & scoping (§0.8 — the four api-nest defects, fixed)

1. **(a) Org identity comes ONLY from the verified Principal.** api-nest's
   `resolveCompanyId()` falls back to the FIRST company row (`memory.service.ts:47-51`,
   `tax-optimizer.service.ts:58-61`) — in multi-tenant that is a cross-org read. The port has
   **no** org parameter anywhere: every service function takes the `Principal` (dataclass at
   `api/app/core/principal.py:53-62`, built solely from a signature-checked Better Auth JWT)
   and uses `principal.org_id`. Never from request body (MASTER_PLAN §0.8: "org_id from
   session context never from request body").
2. **(b) Recall runs under the org GUC.** api-nest `MemorySearchService.recall()` SQL has no
   org filter (`memory-search.service.ts:84-96`). The main api's `audit_log` is already
   per-org and RLS-scoped; recall queries execute on the session where
   `bind_org_guc` (`principal.py:128-146`) has set `app.current_org`, bound on engine checkout
   in both the API (`app/main.py:~137-139`) and the cron path (`app/jobs.py:178-187`). RLS is
   the floor, not the only filter: queries still write `WHERE org_id = :org` explicitly
   (defense-in-depth both directions).
3. **(c) uuid org keys** (schema above).
4. **(d) RLS in the same migration** (schema above).

This is strictly better than industry practice: Mem0 scopes only by application-level
`user_id/agent_id/run_id` identifiers with no DB-enforced org isolation (docs.mem0.ai,
memory-operations — describes managed workspace quotas, no org-separation mechanism); LangMem
isolates via namespace templates like `("memories", "{org_id}")` populated from runtime config
(langmem `dynamically_configure_namespaces` guide). Their one principle we keep: **the
LLM/agent never chooses the tenant; the verified principal does.** DB-enforced RLS below the
application layer means a bug in query construction cannot leak cross-tenant — MASTER_PLAN
risk #3, "Cross-tenant leak → existential."

## A4. §0.4 guardrail — memory is CONTEXT, never a figure source

**Enforcement is mechanical, not prompt-based.** The main api already has the firewall:
`retry.generate_verified()` rejects any claimed number not present in the deterministic facts
set (`api/app/llm/retry.py:39-41,88-100` — `unbacked_numbers` vs `allowed_values(facts)`), and
on exhaustion falls back to a fully fact-backed claim flagged `requires_approval`
(`retry.py:51-63,102-107`). Therefore:

- The org profile + CFO posture inject as a **new labeled context-only block** via a new
  optional `memory: str | None` parameter on `build_user_prompt`
  (`api/app/llm/prompt.py:81`; `SYSTEM_PROMPT` lines 20-28 already restrict numbers to FACTS
  verbatim). Block label ports from api-nest verbatim: *"context only, NEVER a source of
  numbers"* (`memory.service.ts:153-163`).
- Memory content is **NEVER merged into `tools.enrich()`'s facts map**
  (`api/app/llm/tools.py:72-95`). The facts map is the allowed-number set; keeping memory out
  of it preserves §0.4 mechanically — a rupee figure smuggled in via a memory block cannot
  survive verification.
- CI test (the §0.5 "cannot-be-vacuous" check): seed a memory block containing a number absent
  from facts; assert the generated claim either omits it or falls back to the fact-built
  `requires_approval` path. This test fails if anyone ever routes memory into facts.

## A5. Write paths

**Explicit-write only** (operator-curated, api-nest `/api/memory` + append pattern). No LLM
auto-extraction. Rationale: MINJA (arXiv:2503.03704) shows ANY user can poison an agent's
memory bank through normal query interactions alone — no system access needed. For a
zero-error finance product, auto-extracted memory is the attack surface.

- `GET /api/memory` — current blocks + live-rendered org profile.
- `PUT /api/memory` — replace CFO posture; >2200 chars → 422 reject-on-overflow (never
  silent truncation; §0.4 culture).
- `POST /api/memory/append` — append a line, then deterministic LLM-free `consolidate()`
  dedupe (port of `memory.service.ts:24-36`); overflow after consolidation → 422.
- `GET /api/memory/history` — the `org_memory_history` version trail (port of
  `memory.service.ts:124-129`).
- `POST /api/playbook/{id}/feedback` — adopt/dismiss upsert (port of
  `tax-optimizer.service.ts:64-83`).

**Every write is audit-sealed:** `setCfo` semantics port exactly — archive prior version to
`org_memory_history`, then seal a `memory.update` event into the hash-chained audit log
(api-nest `memory.service.ts:66-97`, archive+seal at 76-95), through the main api's audit
chain (choke point: `run_loop`, `api/app/core/loop.py:35`, or direct `audit.append` as the
approvals→audit-write flow already does). This binds to the per-tenant anchored audit chain
the launch checklist requires (MASTER_PLAN §15), giving each company a provable history of
what its CFO agent was told, when its memory changed, and by whom.

**Forgetting = bounded archival, never hard delete** (`evolve()`, api-nest
`memory.service.ts:103-122`): the nightly `evolve` job consolidates and archives, joining the
existing per-org idempotent job framework (`_org_ids`/`JobRun`, `app/jobs.py:143-175`) so it
inherits per-tenant failure isolation and the org GUC for free.

**Future auto-extraction (P2+, not now), defenses pre-committed:** background-not-hot-path
(LangMem's background "memory manager" pattern; matches api-nest
`AGENT_MEMORY_DESIGN.md:141-155` sandboxed post-session reviewer); proposals land in the
existing approvals queue, never directly in the active block; and the two runtime defenses in
A6 below apply regardless.

## A6. Poisoning defenses — remembered text is DATA, not instructions

- **Injection screening:** the assembled memory block passes through the same
  `guardrails.scan_input` injection screen the user query gets (`api/app/llm/maisha.py:55`,
  `api/app/llm/guardrails.py`) before entering the prompt. A memory block that trips the
  screen is dropped from the prompt and the event logged — loudly, not silently.
- **Blast-radius bound:** even a poisoned memory cannot make the product state a wrong figure
  — the `retry.py` number-verification firewall (A4) limits poisoning to narrative tone, which
  Mahsa's fold verdict and the approval gates further contain.
- **Write-path bound:** explicit-write + role gate (A9) + audit seal means every memory byte
  has a named, sealed author.

## A7. Retrieval & injection points

| Consumer | Change |
|---|---|
| `MaishaGenerator.produce` (`api/app/llm/maisha.py:45-83`) | accepts optional `memory` string; passes to `build_user_prompt`; screens via guardrails first. |
| `run_loop` (`api/app/core/loop.py:35`) | fetches org memory (RLS session) and threads it into the generator — single choke point, one diff. |
| Ask Maisha `answer_query` (`api/app/core/ask.py:130-193`) | currently takes no principal/org — thread `Principal` through; inject profile block; episodic recall = lexical search over `audit_log` (org-filtered under GUC, port of `memory-search.service.ts:48-71` FTS/GIN/LIKE fallback ladder). Recall results render as decision+hash citations (existing `Citation` shape at `ask.py:50-54` gains an optional `audit_hash`), never as a number-as-truth. |
| Per-org brief/dunning jobs (`app/jobs.py:90-112,232-249`) | consume the profile block for personalization under the existing org GUC. |
| CFO Profile retrieval | **none** — small enough to always inject (Letta memory-block insight: core memory lives in-context under a budget; archival search is for history). |

Survey §5.3's four-stage retrieval pipeline: the only deltas worth taking are a light query
rewrite and a post-retrieval org+recency filter over the lexical core (already acknowledged in
api-nest `AGENT_MEMORY_DESIGN.md:213-218,253-255`). Nothing else.

## A8. Ports vs rebuilds (from api-nest → `api/app/`)

| Mechanism | Verdict |
|---|---|
| Char-capped explicit-write posture block, reject-on-overflow | **Port** (mechanism, re-typed in Python) |
| Deterministic LLM-free `consolidate()` dedupe | **Port** |
| Archive-on-supersede + `memory.update` audit seal | **Port**, wired to main audit chain |
| `evolve()` bounded archival | **Port**, into `jobs.py` per-org loop |
| Lexical recall over audit log (FTS ladder) | **Port**, + org filter under GUC |
| Playbook adopt/dismiss feedback | **Port** |
| `profileText` context-only label | **Port verbatim** |
| `resolveCompanyId()` first-row fallback | **Rebuild**: Principal-only (A3) |
| `recall()` unscoped SQL | **Rebuild**: org-filtered + RLS (A3) |
| integer `company_id` | **Rebuild**: uuid `org_id` (A2) |
| Tables without RLS | **Rebuild**: RLS in same migration (A2) |

## A9. SPA surface — Settings › Company memory

New tab in `frontend/src/routes/Settings.tsx` (route exists at `App.tsx:135`):

- **View:** live org profile (read-only, labeled "derived from your company records — always
  current") + the CFO posture block with a `n/2200 chars` meter.
- **Edit:** textarea + save (PUT) with the 422 overflow error rendered verbatim; append field.
- **History:** `org_memory_history` list — content, superseded_at, superseded_by, link to the
  sealed audit event. This is the "auditable updates" pillar made visible (survey §7.7).

**OWNER-DECISION (recommendation in bold):** who may edit memory. **Owner/Admin write,
Approver/CA read-only** — memory steers the agent's narrative, so it is an admin surface;
follows the existing RBAC role ladder.

**OWNER-DECISION:** is the memory block visible to the CA seat in Audit Room threads?
**Recommend yes, read-only** — "Audit Room makes the CA look good" (MASTER_PLAN risk #5), and
a CA seeing the standing instructions builds trust; it contains no figures by construction.

**OWNER-DECISION:** keep the 2200-char cap? **Recommend yes, unchanged** — proven in api-nest,
and the cap is the forgetting-pressure mechanism; raising it is a one-line CHECK change later.

## A10. Tickets — Part A

**P0 (one build round):**
- **MEM.P0-1 [OPUS]** Migration `0011_org_memory`: three tables + RLS in same file
  (pattern `0002_multitenant_core.py:123-136`) + SQLAlchemy models. *Verify:* migration test +
  RLS grep-gate (QG.3) green; red-team cross-org read on all three tables fails.
- **MEM.P0-2 [OPUS]** `api/app/core/memory.py` service: get/put/append/consolidate/history +
  playbook feedback, Principal-only org, archive-on-supersede, `memory.update` audit seal,
  422 overflow. REST router `/api/memory` + `/api/playbook/{id}/feedback`, RBAC rows in
  `API_ROUTE_GATES`. *Verify:* service tests incl. overflow-reject, seal-present,
  history-trail; feedback flips quantified savings (port the ₹800→₹0 case).
- **MEM.P0-3 [OPUS]** Prompt injection path: `build_user_prompt(memory=...)` context-only
  block; `guardrails.scan_input` screen on memory text; thread through
  `MaishaGenerator.produce` + `run_loop`. **The §0.4 CI test:** number seeded in memory, absent
  from facts → never survives `generate_verified`; facts map provably untouched. *Verify:*
  that test + existing eval suite green.
- **MEM.P0-4 [OPUS]** Ask threading: `answer_query` takes `Principal`; profile block injected;
  org-filtered lexical recall over `audit_log` under GUC; recall citations carry
  decision+audit_hash. *Verify:* recall returns only own-org rows in a two-org fixture;
  LLM-off mode still answers deterministically.
- **MEM.P0-5 [SONNET]** (deps P0-2) Settings › Company memory tab: view/edit/history + char
  meter + verbatim 422 rendering. *Verify:* route tests + Playwright happy path.

**P1:**
- **MEM.P1-1 [SONNET]** Nightly `evolve` job in the `jobs.py` per-org idempotent loop.
  *Verify:* idempotency test (double-run = no-op).
- **MEM.P1-2 [SONNET]** Brief/dunning personalization from the profile block. *Verify:*
  snapshot tests, numbers unchanged.
- **MEM.P1-3 [SONNET]** Recall polish: light query rewrite + recency post-filter. *Verify:*
  fixture queries rank recent decisions first.
- **MEM.P1-4 [OPUS]** Red-team additions to `tests/redteam/`: memory endpoints + recall under
  hostile org headers. *Verify:* suite green in CI forever (WS4.7).

---

# PART B — CELL-LEVEL CITATION ANCHORS

## B0. Current state (why this exists)

The render surface already exists and is **dead**: `WorkingPanel` renders a Documents block
(`frontend/src/components/VerifiedNumber.tsx:69-165`, block at 133-139) but every assembler
ships it empty (`api/app/web/api_filings.py:185` hardcodes `"documents": []`;
`api/app/web/today.py:55` likewise). Citations today are statutory-only
(`api/app/core/ask.py:50-54`, `api_filings.py:184`); audit-pack `evidence_ref` is a free-form
dotted computation path resolving to nothing mechanically (`api/app/core/audit_pack.py:112`,
e.g. `'ledger.general_ledger:account={code}'` at :190). The vault is already content-addressed
at file granularity — document id IS the sha256 of the text content, integrity re-verified
loudly (`api/app/domains/vault/service.py:56-83,150-154`) — but bank CSV rows have **no
identity at all**: `import_csv` (`api/app/domains/treasury/service.py:159-226`) inserts
positional rows with autoincrement ids, does not keep the file, and re-upload duplicates every
row (:161-162 admits idempotency is unowned). Tally vouchers fall back to positional ids
(`voucher #N`, `api/app/core/tally_import.py:291-292`).

What breaks today: file re-upload (bank rows duplicate; no source link), row re-ordering (any
positional reference silently drifts), and xlsx doesn't exist yet (`audit_pack.py:67-70` —
green-field; pick the stable id now).

## B1. The anchor format (one struct, three locator kinds)

A citation in `working.documents` / `evidence_ref` becomes:

```
{
  doc_sha256:  str,        # vault document id — file-level content address
  file_name:   str,        # display only
  locator:     one of:
     {kind:'csv_row',       source_row: 47}                              # 1-based RAW line number
     {kind:'xlsx_cell',     sheet_id: 2, sheet_name:'Bank', row:47, col:3}
     {kind:'tally_voucher', voucher_id:'V-1023', line: 2}
     {kind:'document'}                                                   # coarse, legacy (B4)
  row_hash:    str,        # sha256(canonical_json([trimmed cell strings in column order]))
  occurrence:  int,        # ordinal among rows with identical row_hash (default 1)
  excerpt:     str         # human string: "Bank stmt HDFC-May.csv, row 47: 12/05 NEFT-000123 ₹1,20,000 Dr"
}
```

Design sources, each load-bearing:

- **`doc_sha256` = raw-bytes hash.** Extend vault ingest with a bytes path (current `ingest`
  hashes decoded/OCR *text*, `service.py:56-57` — binary/CSV raw bytes are never stored).
  Identical bytes dedupe to the same id; changed bytes are a NEW document, so old citations
  still resolve against the immutably stored old file. Existing text-sha path stays for OCR
  docs.
- **`csv_row` uses the SOURCE line number** — RFC 7111 vocabulary (`#row=N`, 1-based), but
  W3C CSVW's *source number* semantics ("the position of the row in the original URL of the
  table", distinct from post-parse row number): checkable against the raw file with zero
  parser config. We take RFC 7111's **syntax**, not its **error model** — its out-of-bounds
  selections "MUST be ignored"/clamped, i.e. silent drift, which §0.4 forbids (B2 inverts it).
- **`xlsx_cell` resolves by `sheetId`, displays `sheet_name`.** ISO/IEC 29500-1: sheet `name`
  "shall be unique" but is user-visible and changes on rename; `sheetId` is "the internal
  identifier for the sheet. This identifier shall be unique" (stable unsignedInt). (Rename
  survival is our inference from internal-id vs display-name, not a spec quote.) Store numeric
  (row, col); render A1 — anchors are machine-resolved, human-rendered.
- **`row_hash` = content identity, Dolt's keyless-table model.** Dolt: without a primary key
  "the keys of the table are effectively the entire row." Bank rows have no trustworthy
  business key (reference columns are frequently blank/duplicated), so identity = hash of
  normalized row content, with `occurrence` distinguishing genuine duplicates (two identical
  NEFT rows). Reuse `app.core.audit.canonical_json` — no new dependency.
- **Provenance shape = W3C PROV-DM:** row-entity `specializationOf` file-entity, figure
  `wasDerivedFrom` row-entity. No PROV serialization — just the structure: the anchor names
  BOTH the containing file (content hash) and the specialized part (locator + row content
  hash), making the figure→row→file derivation chain explicit.
- **Cell-level, not file-level, is also retrieval SOTA:** TableRAG (NeurIPS 2024,
  arXiv:2410.04739) grounds at schema/cell granularity, not whole tables — the answer layer
  should receive and echo cell anchors, never "see file".

## B2. Resolution semantics — verifiable or loudly broken

Given `doc_sha256`: fetch vault bytes (re-verify the file's own sha — existing
`verify_integrity` pattern, `vault/service.py:150-154`), re-extract at the locator, recompute
`row_hash`. Exactly three outcomes, all explicit, none silent:

| Outcome | Condition | Render |
|---|---|---|
| **RESOLVED** | locator present AND row_hash matches | normal citation |
| **MOVED** | locator mismatch, but exactly one row+occurrence in the file matches row_hash | resolves, with a visible "row moved from 47" note — never silently |
| **BROKEN** | zero or ambiguous matches, or doc bytes fail their own sha | working panel states the citation is broken; the figure's badge downgrades from ✓ via the existing `effectiveState` stale-downgrade mechanism (`VerifiedNumber.tsx:54-57`) |

This mirrors RFC 7111's syntax while inverting its silent-clamp error model, and follows the
repo's loud-failure precedents (vault `integrity_ok`, honest-empty 26AS section).

**OWNER-DECISION:** on MOVED, auto-heal the stored locator? **Recommend no** — render-only.
Rewriting stored anchors is a silent mutation of sealed-adjacent data; the row_hash already
guarantees correctness, and a persistent MOVED note is honest signal that the source file
churned.

## B3. Where anchors get MINTED

1. **Bank CSV import (the P0 anchor + the idempotency fix in one move).**
   `import_csv` ingests the raw CSV bytes into the vault FIRST, then stamps each
   `BankTransaction` with four new columns: `source_doc_id` (FK `documents.id`),
   `source_row int`, `row_hash text`, `occurrence int`. Unique constraint
   `(source_doc_id, row_hash, occurrence)` makes re-upload a no-op — fixing the known
   non-idempotent re-import (`treasury/service.py:161-162`) as a side effect of citability.
   Existing rows: columns nullable; legacy rows have NULL anchors and render document-less as
   they do today (no fabricated provenance).
2. **Tally voucher lines.** Replace the positional `voucher #N` fallback
   (`tally_import.py:291-292`) with a voucher content-hash id; store
   `{kind:'tally_voucher', voucher_id, line}` + voucher-hash on committed ledger rows. The
   committed side already links vault docs per voucher (`ca_threads.py:265-268`,
   `api_domains.py:331`) — this extends that precedent to line granularity.
3. **xlsx ingest (green-field, P1).** When xlsx support lands (deliberately not a dependency
   today, `audit_pack.py:67-70`), mint `xlsx_cell` anchors with `sheet_id` from day one.
4. **OCR/vault documents.** Stay file-level (`kind:'document'`) — OCR text has no stable row
   grid; claiming cell precision would be fabricated.

## B4. Where anchors RENDER

1. **Working panel:** assemblers (`api_filings.py:185`, `today.py:55`) populate the
   already-rendered `working.documents` with `{label: excerpt}` + a `/vault` link keyed by
   `doc_sha256`; resolution state (RESOLVED/MOVED/BROKEN) rides along and drives the badge.
2. **Audit pack:** `AuditFigure.evidence_ref` (`audit_pack.py:112`) gains an optional
   `anchors: list[Anchor]` alongside the existing dotted computation path — the path says
   *which computation*, the anchors say *which source rows*. Existing free-form refs stay
   untouched.
3. **Ask:** the `Citation` shape (`ask.py:50-54`) gains optional `anchor` — answers echo cell
   anchors (TableRAG grounding, B1).
4. **Sealing (P1):** include the anchor list in the sealed preview detail
   (`api_filings._seal`, `api_filings.py:202-219` — detail already rides inside the
   hash-chained audit `query` field), so input provenance rides the existing chain with **no
   change to `compute_verdict_hash`** (`verdict.py:46-52` stays `{figures, rule_pack_version,
   org_id}` — the verdict seals outputs; the audit detail seals input provenance).

**OWNER-DECISION:** seal anchors into `_seal` detail in P0 or P1? **Recommend P1** — the
anchors are independently verifiable via row_hash without sealing; sealing is additive and
shouldn't hold the P0 round hostage.

## B5. Migration of existing file-level refs

**They stay file-level, labeled coarser — no fabricated precision.** Existing voucher↔vault
doc links and OCR citations render as `{kind:'document'}` anchors ("Document-level reference")
with no row claim. Nothing is backfilled: a row anchor exists only where the minting path
actually recorded one. Absence renders as absence (§WS2.1 culture: a silent gap is a defect;
an honest "no row-level source recorded" is not).

## B6. Tickets — Part B

**P0 (one build round):**
- **CITE.P0-1 [OPUS]** Vault raw-bytes ingest path: `ingest_bytes(content: bytes)` — sha over
  raw bytes, stored verbatim at `vault/{sha}`, integrity check covers bytes; text-sha path
  untouched for OCR. *Verify:* dedupe + integrity tests; text path regression green.
- **CITE.P0-2 [OPUS]** Treasury vault-first import: migration `0012_bank_row_anchors`
  (4 nullable columns + unique `(source_doc_id, row_hash, occurrence)` on `bank_transactions`;
  table's existing RLS unchanged, no new table); `import_csv` ingests CSV → mints
  `csv_row` anchors with source line numbers + canonical_json row_hash + occurrence.
  *Verify:* re-upload is a no-op (row counts equal); anchors round-trip against the stored
  file; two-identical-rows fixture distinguishes occurrences 1 and 2.
- **CITE.P0-3 [OPUS]** Anchor resolution service (`api/app/core/anchors.py`):
  RESOLVED/MOVED/BROKEN per B2; assemblers populate `working.documents` with excerpts +
  resolution state; `VerifiedNumber` renders MOVED note and BROKEN downgrade via
  `effectiveState`. *Verify:* three-outcome tests (tamper the stored file → BROKEN; reorder
  rows → MOVED with note; untouched → RESOLVED); badge-downgrade UI test.
- **CITE.P0-4 [SONNET]** (deps P0-3) Tally voucher content-hash: replace positional fallback,
  store `tally_voucher` anchors on commit. *Verify:* re-exported/re-ordered Tally file
  resolves same vouchers; positional-fallback grep-gate.

**P1:**
- **CITE.P1-1 [SONNET]** Audit pack: `AuditFigure.anchors` + excerpt rendering in exports.
  *Verify:* snapshot tests.
- **CITE.P1-2 [SONNET]** Ask citations carry anchors; `/vault` deep-link from working panel.
  *Verify:* route tests.
- **CITE.P1-3 [OPUS]** Seal anchor lists into `_seal` detail (audit chain rides input
  provenance). *Verify:* chain verify green; tamper test.
- **CITE.P1-4 [OPUS]** xlsx locator support behind the ingest that introduces openpyxl (or
  equivalent), `sheet_id`-resolved from day one. *Verify:* rename-sheet fixture still
  resolves; name-only resolution is a test failure.

---

## Source register (fetched & verified by the research passes)

Internal: all `file:line` cites above, re-verified against the tree 2026-07-22/23.
api-nest commits `9502175`, `1aaac58`, `c0b075f` verified in git log.
Web: arXiv:2512.13564v2 (memory survey §5.2.2/§5.2.3/§5.3/§7.7); arXiv:2501.13956 (Zep);
arXiv:2504.19413 (Mem0); arXiv:2503.03704 (MINJA); arXiv:2410.04739 (TableRAG);
docs.mem0.ai memory-operations; LangMem dynamically_configure_namespaces guide;
letta.com/blog/memory-blocks; RFC 7111; W3C CSVW tabular data model; W3C PROV-DM (Component 5
"Alternate", Collections); ISO/IEC 29500-1 Sheet element; Dolt versioned-SQL docs (keyless
row identity).

— END SPEC-MEMCITE-1.0 —
