---
name: maisha-mahsa-build
description: Orientation and the master build loop for the Maisha-Mahsa financial suite. Read FIRST when starting any work on this project — it points to the doctrine, the gate, the progress tracker, and the other skills. Triggers: starting a session, "what's next", picking up a module, onboarding.
---

# Building Maisha-Mahsa

You are building a zero-error financial-compliance product. Read `CLAUDE.md` (doctrine) and
`BUILD_PROGRESS.md` (live status) before touching code.

## The architecture in one breath
`Maisha` (Python/FastAPI, `api/`) builds a per-domain **snapshot** and asks `Mahsa`
(Rust DIF sidecar, `dif/`) to **fold** (snapshot→intent) → **validate** (CA-signed rules) →
**unfold** (ResponseShape). Maisha seals the result into a hash-chained audit log and
renders it. Mahsa is the gatekeeper; Maisha never emits an unvalidated number.

## The master loop (every unit of work)
1. **Pick** the next item from `BUILD_PROGRESS.md`, bottom-up (don't build on a red layer).
2. **Read the skill** for that kind of work:
   - a domain module → `skills/domain-module`
   - Rust fold/rules → `skills/rust-dif-core` + `skills/indian-fin-rules`
   - tests → `skills/test-discipline`
   - any UI → `skills/ui-polish`
   - the LLM/eval harness layer (`api/app/llm/`, `api/evals/`) → `skills/harness-layer`
     (see `HARNESS_ENGINEERING.md` + `P0_HARNESS_PLAN.md`)
3. **Build bottom-up**: Rust fold+rules (with property tests) → Python service (exact paise,
   full unit tests) → router/UI → one integration test through the real loop.
4. **Verify**: `make verify` must be green (rust tests + clippy + pytest + ruff + mypy).
5. **Record**: flip the row(s) in `BUILD_PROGRESS.md`; note any PRD deviation.

## The gate
```bash
make verify     # the only definition of "done" for code
make test-rust  # cargo test
make test-py    # pytest unit + integration (spawns the real Mahsa binary)
```

## Hard rules (see CLAUDE.md §2)
- Integer **paise** for money, always. Never a binary float in money math.
- Mahsa is pure & deterministic: no clock/RNG/IO in fold/validate. Inject `as_of`.
- Every rule cites a statute + section. No silent fallbacks, no vacuous tests.
