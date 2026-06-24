# Maisha-Mahsa as a Harness-Engineering Project

> Advisory / strategy document. **Not** governance — `CLAUDE.md` (doctrine) and
> `maisha_mahsa_v4_full_suite_prd.md` (spec) remain the source of truth. This maps
> published harness-engineering work (OpenAI, Anthropic, and others) onto Maisha-Mahsa
> and proposes a prioritized adoption plan. Date: 2026-06-23.

---

## 0. What "harness engineering" means

The *harness* is everything around the raw model weights that turns a model into a
reliable product: the control loop, the tool interface, context construction, output
validation, retries, evals, tracing, and guardrails. The model is fixed; **most
reliability gains come from the harness, not the weights** (the well-known result that
SWE-bench scores move more with harness design than with model swaps). Every serious lab
now publishes harness components separately from models.

## 1. Where Maisha-Mahsa stands today (verified against the code)

| Half of a harness | Status | Evidence |
|---|---|---|
| **Verifier / gate** (deterministic recompute the model can't bypass) | ✅ Built | `dif/` Mahsa fold→validate→unfold; `core/mahsa_client.py`; Golden Rule in `CLAUDE.md §1` |
| **Tamper-evident trace** (audit trail) | ✅ Built (foundation) | `core/audit_store.py` hash-chained `audit_log` |
| **Routing** (classify → dispatch to domain) | ✅ Built | `core/router.py` DomainRouter |
| **Human-in-the-loop interrupt** (approval queue) | ✅ Partial | Yellow/Red → approval email; dashboard approvals queue |
| **Generator** (the "Maisha" LLM layer: tools, narrative, `action_claim`) | ❌ **Not built** | No LLM client in `api/app`; `run_loop` is deterministic snapshot→fold→audit; CFO brief is pure templates (`core/cfo.py`) |
| **Measurement** (eval/bench harness for the LLM layer) | ❌ **Not built** | No eval/bench dir; `make verify` covers calc/rules, not model behavior |
| **Optimizer loop** (regenerate on validation failure) | ❌ Not built | `run_loop` has no LLM retry path |

**Thesis:** the project built the *gate before the generator* — the correct, rare order.
Most agent projects bolt verification on last. The work ahead is to build the generator
and the measurement layers *to the standard the gate already sets* (zero-error,
deterministic, cited, auditable).

---

## 2. Published harness work → adoption for Maisha-Mahsa

Each row: the external project/principle, the lesson, and the concrete adoption here.

### 2.1 Anthropic — *Building Effective Agents* (Dec 2024): workflows > agents
**Lesson:** prefer deterministic *workflows* (prompt-chaining, routing, evaluator-optimizer)
over open-ended autonomous agents; reach for autonomy only when the task demands it.
**Adopt:** Frame Maisha-Mahsa explicitly as an **evaluator-optimizer + routing workflow**,
not an autonomous agent — correct for a zero-error finance product. The DomainRouter is the
*router*; Mahsa is the *evaluator*. The missing piece is the *optimizer* edge: feed Mahsa's
RED + triggered-rule citation back to the LLM to revise (§2.5).

### 2.2 OpenAI — Structured Outputs / strict JSON-schema function calling (2024)
**Lesson:** constrain the model to emit schema-valid JSON; never parse free text for
critical fields.
**Adopt:** `action_claim` must be a **strict typed schema** — amounts as integer-paise
strings, `domain` as enum, every claimed number tagged with the tool call that produced it,
mandatory `statute`/`section` for any rule assertion. Use constrained decoding: Ollama's
`format: <json-schema>` for the local model; tool-use schema enforcement for Claude. This
kills a class of malformed-number bugs *before* Mahsa runs.

### 2.3 SWE-agent — Agent-Computer Interface (ACI) design (Princeton, 2024)
**Lesson:** tool ergonomics dominate agent performance — tools must be designed *for the
model*, with concise outputs, validation, and good error messages it can recover from.
**Adopt:** Maisha's tools (`calculator`, `ledger_query`, `scenario_engine`,
`tax_calculator`, `gst_validator`, `payroll_engine`) must be **thin wrappers over the
existing deterministic Python calc functions** (`*_calc.py`) — the LLM never does
arithmetic itself. Each tool returns structured, citation-bearing results and a precise
error string on bad input so the model self-corrects rather than hallucinating.

### 2.4 OpenAI Agents SDK (ex-Swarm): guardrails + tracing (2025)
**Lesson:** run input/output *guardrails* alongside the model; *trace* every step.
**Adopt:**
- **Output guardrail** = Mahsa (already). 
- **Input guardrails** (new, important): email replies and scheduled-job inputs are a
  **prompt-injection vector**. Add an input guard for injection/jailbreak patterns and a
  **PII-redaction pass** before any text reaches a *cloud* model (Ollama is local, but the
  Claude fallback sends data off-box).
- **Tracing**: extend `audit_log` into a full trace — prompt hash, model id+version,
  temperature, token counts, each tool call + result, retry count, latency. The hash chain
  already gives tamper-evidence for free.

### 2.5 ReAct + Reflexion (2023): reason-act-observe + self-correction
**Lesson:** let the model observe failures and revise.
**Adopt:** the **evaluator-optimizer retry loop**. When Mahsa returns RED (or a rule fires),
hand the triggered rule id + statute citation back to the LLM and let it regenerate —
**bounded** (e.g. ≤2 retries) for determinism and cost. If it still fails, fall back to the
deterministic template and flag for human approval. This is the single biggest behavioral
upgrade to `run_loop`.

### 2.6 Evals as first-class — OpenAI Evals, UK AISI *Inspect*, **τ-bench**, terminal-bench
**Lesson (the big one):** measure with **pass^k** (consistency across *k* runs), not pass@1.
A finance model that's right 8/10 times is *dangerous*, not 80% good.
**Adopt:** build a **golden eval harness** — curated `(DB fixture, user query,
ground-truth action_claim)` cases per domain. Metrics:
1. **Exact match to Mahsa-recomputed numbers** (paise-exact, the only acceptable bar).
2. **pass^k consistency** — run each case *k* times at temp=0 and require identical claims.
3. **Citation correctness** — every rule assertion cites the right statute/section.
4. **Refusal/abstain rate** — does it decline when data is insufficient instead of guessing?

Wire it as a CI gate next to `make verify` (e.g. `make eval`). This is what makes the LLM
layer shippable in a zero-error product. Style it after Inspect/Evals (declarative cases +
scorers).

### 2.7 DSPy (Stanford): compile prompts against a metric
**Lesson:** optimize prompts/few-shots *automatically* against an eval set instead of
hand-tuning — especially valuable for small, prompt-sensitive local models.
**Adopt:** once §2.6 exists, add a DSPy-style **compile step** that optimizes the Maisha
system prompt + per-domain few-shot exemplars against the golden set. Qwen3-14B (the local
default) will benefit disproportionately. The eval set is the prerequisite — build it first.

### 2.8 OpenAI — *Let's Verify Step by Step* / process supervision (2023)
**Lesson:** verify *intermediate* steps, not just the final answer.
**Adopt:** make **tool outputs themselves Mahsa-checkable**, not only the final
`action_claim`. Each calc-tool result is a verifiable artifact; a wrong intermediate is
caught at the step, not the end. Aligns with the existing fold-everything design.

### 2.9 Anthropic — Model Context Protocol (MCP) (Nov 2024)
**Lesson:** standardize tools/resources as servers reusable across clients.
**Adopt (P2):** expose each domain's calc tools as an **MCP server**. Then the same verified
tools are reachable by the Maisha harness, by Claude Code during development, or by future
clients — one definition, no duplication. Lower priority but clean architecture.

### 2.10 LangGraph: checkpointed, durable, human-in-the-loop graphs
**Lesson:** model the agent as a state machine with checkpoints and resumable interrupts.
**Adopt:** formalize the loop as a small **state machine with checkpoints** so a brief
generation can *pause* at an approval interrupt and *resume* — important for the durable,
scheduled **8pm CFO brief** (the pending L5 cron item). Durability matters because a partial
financial dispatch is worse than none.

---

## 3. Prioritized adoption plan

### P0 — unlocks the product (build in this order)
1. **Golden eval harness** (§2.6) — `evals/` with per-domain cases, paise-exact + pass^k
   scorers, `make eval` CI gate. *Build first: it defines "done" for everything below.*
2. **Maisha LLM layer** (§2.2, §2.3) — LLM client (Ollama-first, Claude fallback per
   `CLAUDE.md §7`), strict `action_claim` schema via constrained decoding, tools as thin
   wrappers over `*_calc.py`. Slot into `run_loop` *before* the Mahsa fold.
3. **Evaluator-optimizer retry loop** (§2.5) — bounded regenerate-on-RED, deterministic
   template fallback, human-approval flag on exhaustion.

### P1 — reliability & safety
4. **Input guardrails** (§2.4) — injection detection + PII redaction before any cloud call.
5. **Full tracing** (§2.4) — extend `audit_log` to capture prompt/model/tokens/tools/retries.
6. **Determinism hygiene** — temp=0, pinned model id+version, prompt hash in every trace
   entry, graceful degradation when the LLM is unavailable (template path already exists for
   the brief).

### P2 — optimization & scale
7. **DSPy-style prompt compilation** (§2.7) against the eval set.
8. **MCP tool servers** (§2.9).
9. **Cost/latency budgets** per call + **eval-gated model routing** (Ollama→Claude only when
   the local model fails eval thresholds for a domain).

---

## 3a. Implementation status (2026-06-24)

| Item | Status |
|---|---|
| P0-① golden eval harness (paise-exact + pass^k, `make eval`) | ✅ done |
| P0-①b eval cases — all 12 domains (13 cases) | ✅ done |
| P0-② Maisha LLM generator (Ollama/Claude constrained decode, calc-wrapping tools) | ✅ done |
| P0-③ evaluator-optimizer retry loop (fact-fidelity, bounded retry, fallback) | ✅ done |
| P1-4 input guardrails (injection block + cloud PII redaction) | ✅ done |
| P1-5 tracing — `llm_trace` table (hashes, model, attempts, verified, latency) | ✅ done (token counts deferred) |
| P1-6 determinism hygiene (temp 0, pinned model label, repro hashes) | ✅ done |
| P2-9 eval-gated model routing (`routing.py`) + latency capture | ✅ done |
| P2-7 DSPy-style prompt compilation | ⏸ scaffolding-only — needs a live model + the eval set to optimize against |
| P2-8 MCP tool servers | ⏸ deferred — needs the `mcp` dependency; tools already centralized in `llm/tools.py` for a clean lift |

Everything ✅ is covered by `make verify` (Rust + Python + `make eval`). The ⏸ items are
gated on a running Ollama/Claude (DSPy optimizes prompts *against measured eval scores*, which
requires a live model) or a new dependency (MCP); both are low-risk lifts when that's available.

## 4. One-line summary

Maisha-Mahsa already nailed the principle every harness paper converges on — *a
deterministic verifier the model cannot bypass, with an auditable trail*. The roadmap is to
build the **generator** (structured-output LLM layer with calc-wrapping tools and a bounded
retry loop) and the **measurement** layer (a pass^k golden-eval gate) to the same zero-error
standard the gate already enforces.
