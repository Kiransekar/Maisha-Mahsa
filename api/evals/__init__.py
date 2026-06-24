"""The Maisha golden-eval harness (P0-① — see HARNESS_ENGINEERING.md §2.6, P0_HARNESS_PLAN.md).

Curated ``(seed, query, ground-truth)`` cases per domain, scored on **paise-exact** match,
**pass^k** run-to-run consistency, **citation correctness**, and **abstain-when-thin**.
A finance product has no tolerance band on numbers, so the gate is exact.

In P0-① there is no LLM yet: the harness runs against a :class:`ScriptedProducer` (canned
claims) to prove the harness + scorers themselves work. P0-② swaps in the real LLM producer;
nothing else about the harness changes.
"""
