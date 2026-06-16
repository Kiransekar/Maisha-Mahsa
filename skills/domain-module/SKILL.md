---
name: domain-module
description: The repeatable bottom-up recipe for building one of the 12 Maisha-Mahsa domain modules (treasury, revenue, payables, payroll, gst, tax, ledger, forecast, equity, compliance, expense, vault). Use when implementing or extending any domain. Treasury (api/app/domains/treasury) is the reference implementation — copy its shape.
---

# Building a domain module

Every domain has the **same shape** so it is uniform and independently testable. The
reference, fully wired example is `api/app/domains/treasury/`.

## File layout (mirror treasury)
```
api/app/domains/<domain>/
  __init__.py     exports the service
  manifest.py     DomainManifest — the PRD feature list + build state (unit of progress)
  schemas.py      Pydantic request/response models
  models.py       (or add to api/app/db/models/<domain>.py) SQLAlchemy tables, money = INTEGER paise
  service.py      subclass BaseDomainService; exact-paise business math; build_snapshot()
  router.py       thin FastAPI routes -> service / run_loop
  rules.py        mirror of the rule IDs this domain owns (authoritative logic is in dif/)
```

## Steps (bottom-up — do not skip the order)
1. **Rust first.** Add the domain sub-vector fold in `dif/src/fold/<domain>.rs`, register it
   in `dif/src/fold/mod.rs::domain_fold`, and add any rules to `dif/rules/rules.yaml`
   (see `skills/indian-fin-rules`). Add property tests in `dif/tests/`. `cargo test` green.
2. **Models + schema.** Add ORM models (INTEGER paise), import them in
   `api/app/db/models/__init__.py`, and mirror the DDL into `api/app/db/schema.sql`.
3. **Service.** Implement `BaseDomainService`. `build_snapshot(session, as_of=None)` returns
   the exact-paise snapshot dict Mahsa expects. Keep it pure/deterministic given the rows.
4. **Register.** Replace the `PendingDomainService` entry in `api/app/domains/__init__.py`
   with the real service; set good `keywords` for the DomainRouter.
5. **Router + UI.** Add routes; build the domain page per `skills/ui-polish`.
6. **Tests.** Unit-test the service math exhaustively (`tests/unit/<domain>/`); add at least
   one integration test through `run_loop` against the real Mahsa binary
   (`tests/integration/`). See `skills/test-discipline`.
7. **Manifest + progress.** Flip features to `DONE` in `manifest.py`; update `BUILD_PROGRESS.md`.
   A module is done only when its manifest `is_complete` and `make verify` is green.

## Snapshot contract
`build_snapshot` returns a dict with `as_of` (ISO date) and money fields in **paise**.
Generic numeric signals a rule needs go in a `metrics` sub-dict (the Rust `Snapshot.metrics`
bag). Match the metric names used by your rules in `dif/rules/rules.yaml`.

## Don't
- Don't decide Green/Yellow/Red in Python — that's Mahsa's job.
- Don't let a half-built domain emit a zero snapshot — keep it `PendingDomainService` until real.
- Don't store money as REAL/float. Paise integers only.
