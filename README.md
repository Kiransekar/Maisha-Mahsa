# Maisha-Mahsa

The complete startup financial suite for the Indian regulatory context. A single-user,
open-source, self-hosted "virtual CFO": **Maisha** (Python/FastAPI) orchestrates and talks
to a local LLM, while **Mahsa** (a 12 MB Rust DIF sidecar) is the deterministic gatekeeper
that recomputes and validates every number against CA-signed rules before a human sees it.

> **What** to build: [`maisha_mahsa_v4_full_suite_prd.md`](./maisha_mahsa_v4_full_suite_prd.md)
> **How** we build it: [`CLAUDE.md`](./CLAUDE.md) · **Where we are:** [`BUILD_PROGRESS.md`](./BUILD_PROGRESS.md)
> **What's left to launch (do this in order):** [`LAUNCH_READINESS.md`](./LAUNCH_READINESS.md)

## Layout

```
Maisha-Mahsa/
├── dif/        Mahsa — Rust DIF core (fold / validate / unfold). Pure, deterministic.
├── api/        Maisha — Python service: core, 12 domain modules, web UI, tests.
├── infra/      docker-compose (api + dif + redis + mailhog + ollama), Caddy, env.
├── skills/     Project build skills — read the relevant one before a module.
└── Makefile    `make verify` is the gate.
```

## Quick start (local dev)

```bash
# 1. Mahsa (Rust) — needs rustup/cargo
cd dif && cargo test && cargo run        # serves http://127.0.0.1:8088

# 2. Maisha (Python)
make venv                                # creates api/.venv, installs api[dev]
cd api && .venv/bin/uvicorn app.main:app --reload   # http://127.0.0.1:8000

# 3. The gate (run before marking anything done)
make verify                              # rust tests + clippy + pytest + ruff + mypy
```

`make dev` brings up the whole stack in Docker (api, dif, redis, mailhog, ollama).

## Status

Foundation is green and bottom-up verified: the Rust core (27 tests, clippy-clean) and the
Python layer (30 tests incl. a real-binary end-to-end loop) both pass. **Treasury** is the
first complete vertical slice (CSV import → cash/burn/runway → Mahsa fold/validate →
hash-chained audit). The other 11 domains are scaffolded with the shared contract and are
built one at a time. See `BUILD_PROGRESS.md`.

## Non-negotiables

- **Mahsa is the gatekeeper.** Maisha never emits a final number Mahsa hasn't recomputed.
- **Exact money.** Integer paise everywhere internally; never a binary float in money math.
- **Zero error tolerance.** `make verify` must be green before a module is "done".
- **Auditable.** Every decision is sealed into an append-only, hash-chained audit log.
