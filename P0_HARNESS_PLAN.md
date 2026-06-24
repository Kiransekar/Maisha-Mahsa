# P0 Harness Layer — Implementation Plan

> Companion to `HARNESS_ENGINEERING.md`. This is the concrete, file-level plan for the three
> P0 work items, written to the project's existing conventions (`CLAUDE.md`, the skills, the
> `make verify` gate). **Build order is fixed**: ① eval harness → ② Maisha LLM layer →
> ③ retry loop. Nothing here weakens the Golden Rule — the LLM still never emits a number
> Mahsa hasn't recomputed. Date: 2026-06-23.

---

## Invariants this plan must not break
- **Golden Rule**: every number reaches a human only after Mahsa recompute (`CLAUDE.md §1`).
  The LLM layer slots into `run_loop` **before** the existing `mahsa.fold` call — it never
  replaces it.
- **Integer paise** end-to-end; rupees only at the edge. The LLM emits paise as strings; the
  schema validator parses to `int`.
- **Determinism**: temp=0, pinned model id, injected `as_of`/timestamp (no clock/RNG in
  Mahsa). The LLM is non-deterministic, which is exactly *why* §2.6's pass^k eval exists and
  *why* Mahsa stays the gate.
- **Gate**: `make verify` stays green; add `make eval` as a second, model-aware gate.
- **Graceful degradation**: if the LLM is down/unconfigured, the system falls back to the
  existing deterministic snapshot/template path (already true for the CFO brief) — never a
  silent wrong answer.

---

## ① Golden eval harness  (build first — defines "done" for ② and ③)

**Why first:** with no metric, "the LLM layer works" is unfalsifiable. The eval set is the
acceptance test for everything downstream and needs **no LLM to author** (cases are
hand-written ground truth).

### Layout (mirrors `api/tests/unit/<domain>/`)
```
api/evals/
  __init__.py
  harness.py          # case loader + runner + scorer registry
  scorers.py          # paise_exact, pass_k_consistent, citation_correct, abstains_when_thin
  report.py           # pretty + machine-readable (JSON) results
  cases/
    treasury/*.yaml   # one file per scenario
    revenue/*.yaml
    ... (12 domains)
  conftest.py         # fixtures: seeded in-memory SQLite per case, stub vs real LLM
api/tests/unit/evals/test_harness.py   # the harness itself is unit-tested (no vacuous passes)
```

### Case format (declarative, Inspect/OpenAI-Evals style)
```yaml
id: treasury-runway-01
domain: treasury
fixture: treasury/seed_low_runway.sql      # or a fixture-builder ref
query: "What's our runway and should I be worried?"
expect:
  action_claim:
    runway_months: "4"                      # ground truth, recomputed by hand + Mahsa
    cash_paise: "1250000000"
  citations: []                             # e.g. ["MSMED Act 2006 s.15"] when a rule applies
  must_abstain: false
  expected_status: yellow                   # Mahsa verdict the claim should produce
k: 5                                         # pass^k runs
```

### Scorers (`scorers.py`)
1. `paise_exact` — every numeric field in `action_claim` matches ground truth **and** matches
   Mahsa's recompute of the same snapshot (the only acceptable bar).
2. `pass_k_consistent` — run the case `k` times at temp=0; **all** runs must produce the
   identical claim. Report `pass^k` per case and aggregate. (τ-bench's core metric.)
3. `citation_correct` — every rule assertion cites the statute/section Mahsa's triggered rule
   carries; no missing, no fabricated citations.
4. `abstains_when_thin` — for `must_abstain: true` cases (insufficient data), the LLM must
   decline, not guess.

### Gate
```make
eval: ## Model-aware quality gate for the Maisha LLM layer
	cd api && .venv/bin/python -m evals.harness --all --report json
```
- Runs in two modes: **stub LLM** (deterministic fake that returns canned claims — runs in
  CI without a model, proves the harness itself works) and **real LLM** (Ollama, run
  locally/nightly). CI gate uses stub for the harness's own correctness; real-model
  thresholds are tracked in `BUILD_PROGRESS.md`, gated before flipping the LLM-layer row.
- Thresholds (initial): `paise_exact == 100%`, `pass^5 == 100%` on a "core" case subset,
  citation_correct == 100%. A finance product has no tolerance band on numbers.

### Test discipline
- The harness, scorers, and case loader get their own unit tests (`skills/test-discipline`):
  a scorer that always passes is a vacuous test → failure. Include at least one **negative
  case** per scorer (a deliberately wrong claim that must score 0).

---

## ② Maisha LLM layer  (the generator)

### New files
```
api/app/llm/
  __init__.py
  client.py          # LLMClient protocol; OllamaClient (httpx) + ClaudeClient (fallback)
  schema.py          # ActionClaim pydantic model (strict) + JSON-schema export for constraint
  tools.py           # tool registry: thin wrappers over existing *_calc.py
  prompt.py          # system prompt + per-domain prompt assembly (pure, testable)
  maisha.py          # generate(snapshot, query, domain) -> ActionClaim  (the orchestrator)
api/tests/unit/llm/test_schema.py test_tools.py test_prompt.py test_maisha_stub.py
```

### `ActionClaim` schema (`schema.py`) — strict, constrained
- All money fields typed `PaiseStr` (string of digits, validated → `int`; rejects floats).
- `domain: DomainEnum`; `narrative: str`; `claims: dict[str, PaiseStr]`;
  `rule_assertions: list[{rule_id, statute, section}]`; `confidence`; `abstained: bool`.
- Export `ActionClaim.model_json_schema()` and feed it to the model as a **hard constraint**:
  - Ollama: `format=<json schema>` on the generate call (constrained decoding).
  - Claude: a single forced tool whose `input_schema` is the same schema.
- This is OpenAI Structured Outputs / SWE-agent ACI applied: the model *cannot* emit a
  malformed claim; bad input to a tool returns a precise error the model can recover from.

### Tools (`tools.py`) — wrappers over deterministic calcs, **never** LLM arithmetic
Each PRD tool maps to existing code (no new math):
| Tool | Wraps |
|---|---|
| `calculator` | a fixed-point paise helper over `core/money.py` (no float) |
| `ledger_query` | `domains/ledger/ledger_calc.py` (TB/P&L/BS reads) |
| `tax_calculator` | `domains/tax/tax_calc.py` |
| `gst_validator` | `domains/gst/gst_calc.py` (e.g. `validate_gstin`, `compute_gstr3b`) |
| `payroll_engine` | `domains/payroll/statutory.py` |
| `scenario_engine` | `domains/forecast/forecast_calc.py` |
Tools return structured, citation-bearing results; on bad args they return a typed error
string. Tool outputs are themselves Mahsa-checkable artifacts (§2.8 process supervision).

### LLM client (`client.py`) — config-driven, Ollama-first
Add to `config.py` (env-prefixed `MAISHA_`):
```python
llm_provider: str = "ollama"          # "ollama" | "claude" | "stub"
ollama_url: str = "http://127.0.0.1:11434"
ollama_model: str = "qwen3:14b"
claude_model: str = "claude-opus-4-8" # fallback, per CLAUDE.md §7 (only when enabled)
llm_temperature: float = 0.0          # determinism
llm_max_retries: int = 2              # for the §3 optimizer loop
llm_timeout_s: float = 30.0
```
`StubClient` returns scripted claims so unit tests and the CI eval run without a model.

### Wiring into `run_loop`
`run_loop` gains an optional LLM step **before** the fold:
```
snapshot = service.build_snapshot(...)            # unchanged
if query and settings.llm_provider != "off":
    claim = await maisha.generate(snapshot, query, service.domain)   # NEW
    snapshot = merge_claim_into_snapshot(snapshot, claim)            # claim is data, not verdict
fold = await mahsa.fold(snapshot, domain=..., query=query)           # unchanged — still the gate
# audit entry now also records: model id, prompt hash, claim hash, retry count
```
The claim is **never** trusted as a verdict — Mahsa still folds/validates. If the LLM is off
or errors, `run_loop` behaves exactly as today.

---

## ③ Evaluator-optimizer retry loop  (the optimizer edge)

When Mahsa returns RED (or a rule triggers) on a claim-derived snapshot:
1. Build a **feedback message** from `fold.validation.triggered` (rule id + statute + section
   + action) — ReAct/Reflexion-style observation.
2. Re-invoke `maisha.generate` with the feedback appended, **bounded by `llm_max_retries`**.
3. On success → proceed. On exhaustion → fall back to the deterministic template path **and**
   set `requires_approval` (human-in-the-loop interrupt, §2.10), recording the exhaustion in
   the audit trail.
4. Every attempt is a separate audit/trace entry (full tracing, §2.4) — prompt hash, model,
   tokens, latency, retry index, Mahsa verdict.

Determinism note: bounded + temp=0 keeps the loop reproducible; the pass^k eval (§①) guards
against a model that oscillates across runs.

---

## Sequencing & gates
| Step | Deliverable | Gate before marking ✅ in BUILD_PROGRESS.md |
|---|---|---|
| ①a | harness + scorers + 2 domains of cases | `make verify` green; harness unit tests incl. negative cases |
| ①b | cases for all 12 domains | `make eval` (stub) == 100% on harness; real-model baseline recorded |
| ②a | schema + tools + stub client + unit tests | `make verify` green |
| ②b | Ollama/Claude clients + run_loop wiring | `make verify` green; one integration test through real loop |
| ③ | retry loop + tracing fields | `make verify` + `make eval`; retry/abstain cases pass |

## New skill
`skills/harness-layer/SKILL.md` — the repeatable recipe for this layer (see that file). Read
it before any work under `api/app/llm/` or `api/evals/`.

## Out of scope for P0 (tracked as P1/P2 in HARNESS_ENGINEERING.md §3)
Input guardrails (injection/PII), MCP tool servers, DSPy prompt compilation, cost/latency
budgets, eval-gated model routing.
