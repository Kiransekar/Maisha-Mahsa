---
name: harness-layer
description: How to build the Maisha LLM/agentic "harness" layer — the eval harness (api/evals/), the LLM generator (api/app/llm/), and the evaluator-optimizer retry loop — to the project's zero-error standard. Use for any work under api/app/llm/ or api/evals/, or when wiring the LLM into run_loop. Enforces the Golden Rule: the LLM never emits a number Mahsa hasn't recomputed. See HARNESS_ENGINEERING.md (why) and P0_HARNESS_PLAN.md (what/where).
---

# Building the Maisha harness layer

You are building the **generator** and **measurement** halves of an LLM harness on top of a
gate (Mahsa) that already exists. Read `HARNESS_ENGINEERING.md` (the thesis + the mapping
from published harness work) and `P0_HARNESS_PLAN.md` (the file-level plan) first. Then
`CLAUDE.md §1–2` (Golden Rule, zero-error).

## The one rule that governs this layer
**The LLM is a drafter, not a decider.** Its `ActionClaim` is *data fed into* the existing
`mahsa.fold` — never a verdict, never a number shown to a human un-recomputed. The LLM step
slots into `run_loop` **before** the fold; if it is off or errors, the loop must behave
exactly as it does today (deterministic snapshot/template path). No silent wrong answers.

## Build order (do not reorder)
1. **Eval harness first** (`api/evals/`). With no metric, "it works" is unfalsifiable.
   Author ground-truth cases by hand — needs no model. Build the scorers
   (`paise_exact`, `pass_k_consistent`, `citation_correct`, `abstains_when_thin`) and give
   each a **negative case** (a wrong claim that must score 0) — a scorer that can't fail is a
   vacuous test (`skills/test-discipline`).
2. **LLM generator** (`api/app/llm/`): strict `ActionClaim` schema → constrained decoding
   (Ollama `format`, Claude forced tool) → tools that are **thin wrappers over the existing
   `*_calc.py`** (the LLM never does arithmetic) → `StubClient` so CI/unit tests run with no
   model.
3. **Retry loop**: on Mahsa RED, feed `validation.triggered` (rule + statute/section) back to
   the LLM, bounded by `llm_max_retries`; on exhaustion fall back to template + flag for
   approval. Every attempt is its own audit/trace entry.

## Hard constraints (in addition to CLAUDE.md)
- **Money**: LLM emits paise as digit-strings; the schema parses to `int`. Reject floats.
- **Determinism**: temp=0, pinned model id. Record model id + prompt hash + claim hash +
  retry index in the audit entry. The pass^k eval guards run-to-run drift.
- **Tools wrap, never compute**: every tool delegates to a deterministic calc function and
  returns structured, citation-bearing results; on bad args it returns a precise error the
  model can recover from (SWE-agent ACI discipline).
- **Citations**: any rule assertion must carry the statute/section Mahsa's triggered rule
  carries — no missing, no fabricated (`skills/indian-fin-rules`).

## The gate
```bash
make verify   # unchanged: rust + pytest + lint + mypy — still green
make eval     # new: model-aware. Stub mode in CI (proves the harness); real Ollama nightly/local.
```
Thresholds for the LLM layer (record in `BUILD_PROGRESS.md` before flipping a row):
`paise_exact == 100%`, `pass^k == 100%` on the core subset, `citation_correct == 100%`.
A finance product has no tolerance band on numbers.

## Where things live
| Concern | Path |
|---|---|
| Why (strategy, published-work mapping) | `HARNESS_ENGINEERING.md` |
| What/where (file-level plan) | `P0_HARNESS_PLAN.md` |
| Eval harness | `api/evals/` |
| LLM generator | `api/app/llm/` |
| The loop the LLM slots into | `api/app/core/loop.py` |
| The gate it never bypasses | `api/app/core/mahsa_client.py`, `dif/` |
