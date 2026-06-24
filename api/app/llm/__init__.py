"""The Maisha LLM/harness layer (PRD §10 Layer 1). The model is a *drafter*, not a decider:
it emits a strict :class:`~app.llm.schema.ActionClaim`, which the existing Mahsa loop then
recomputes and validates (the Golden Rule, CLAUDE.md §1). This package holds the claim
schema now; the generator/tools/retry loop land in P0-② and P0-③ (see P0_HARNESS_PLAN.md).
"""
