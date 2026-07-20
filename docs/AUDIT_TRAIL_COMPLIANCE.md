# Audit-Trail Compliance (MCA) — WS4.4

Maps Maisha-Mahsa's per-tenant hash-chain to the MCA audit-trail ("edit log") mandate under
the Companies (Accounts) Rules, 2014 r.3(1) proviso — books of account kept electronically
must use software that (a) records an **edit log** of every change, (b) captures the **date**
each change is made, and (c) ensures the edit log **cannot be disabled**.

Scope of this document: the mechanism (`app/core/audit.py`, `app/core/audit_store.py`) and how
it satisfies each requirement. Wiring the edit-log helper into every accounting write is WS4.2;
external timestamp submission is ops/Human.

## Requirement → mechanism

| MCA requirement | How it is met | Where |
|---|---|---|
| Edit log of every change | `edit_log_payload(...)` builds one audit entry per accounting record create/update/delete; appended to the tenant chain | `audit.edit_log_payload`, `audit_store.append_for` |
| Date of each change | `timestamp` is part of the hashed `core_payload` — cannot be altered without breaking the chain | `audit.AuditEntry.core_payload` |
| Cannot be disabled | The write path calls the helper unconditionally (no feature flag / no config toggle). Append-only table: application code never `UPDATE`/`DELETE`s `audit_log` | WS4.2 wiring + `AuditLog` docstring |
| Tamper-evident | `this_hash = sha256(prev_hash ‖ canonical_json(entry))`; changing any historical field breaks every later hash. Detected by `verify_chain(...)` in O(n), no secrets | `audit.compute_hash`, `audit.verify_chain` |

## Per-tenant isolation (WS4.4 core)

Each org has an **independent chain** rooted at `tenant_genesis(org) = sha256("maisha-audit-genesis:" ‖ org)`,
which is distinct per tenant and distinct from the legacy global `GENESIS_HASH`.

- **Genesis per tenant.** A tenant's first entry chains onto *its own* genesis, so entries from
  org A can never be replayed into org B (the org id is bound into the first link).
- **No interleave.** Entries from all tenants persist in the one `audit_log` table, but each
  tenant's chain is reconstructed by following its hash links from its genesis
  (`audit_store.load_chain_for`). Two tenants never share a `prev_hash`, so the chains are
  disjoint by construction — no org column is required for the separation. (Persisting an
  explicit `org_id` column is a WS4.1/WS4.2 schema/migration concern; the chain math here does
  not depend on it.)
- **Per-tenant verify.** `audit_store.verify_chain_for(session, org)` — the `/audit/verify`
  per-tenant capability — validates exactly that org's chain and is blind to every other. A
  tamper in one tenant is caught by that tenant's verify and does not affect any other tenant's
  result. (Route wiring is WS4.3, once sessions carry `org_id`.)

The underlying `canonical_json` / `compute_hash` algorithm is **unchanged** — other code and the
Mahsa verdict hash depend on it. Per-tenant separation is achieved solely via the genesis value,
which reuses the existing primitive.

## Daily chain-root anchoring

`compute_daily_root(org, day, entries)` (store wrapper `compute_daily_root_for`) produces an
`AnchorRecord{org, day, root, entry_count, external_ref}`. `root` deterministically commits to
every entry the tenant sealed that day — change any entry and the root changes.

The `root` is submitted to an **independent timestamp authority** (RFC-3161 TSA, or a public
blockchain anchor) so the day's books cannot be back-dated even by someone with full DB access.
That external submission — and writing the returned reference into `external_ref` — is an
**ops/Human integration** and is deliberately not performed in this module.

## Boundaries / notes

- **No PII in the log** (§0.8). The edit-log entry carries opaque keys (`record_type`,
  `record_id`) and `before`/`after` content **hashes** only — never record content.
- **Non-disablable is enforced at the call site**, not here: the helper only produces the entry.
  WS4.2 must ensure every books-of-account write path calls it with no bypass.
- **Product-confirmable (§0.6):** the retention window for anchored roots and the choice of
  external timestamp authority (TSA vs. chain) are operational policy, not statutory values
  fixed by this spec — flagged for product/ops confirmation, not blocking.
