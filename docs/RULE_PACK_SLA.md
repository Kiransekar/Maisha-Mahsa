# Rule-pack update SLA & operations (WS1.E3)

The statutory rule pack (`dif/rules/rules.yaml` + `dif/rules/MANIFEST.yaml`) is **data, not
code**: rules, statutory citations, and the action copy tenants read. This document is the
published contract for how fast the pack tracks the law, how a pack ships, how a tenant sees
which pack they are on, and how a bad pack is rolled back.

## 1 · Update SLA by trigger

| Trigger | What changes | SLA (from publication of the instrument) |
|---|---|---|
| **Union Budget day / Finance Act** (rates, slabs, thresholds, new sections) | affected rules + oracle vectors | draft pack within **2 business days** of the Finance Bill text; final pack within **5 business days** of enactment; transition-boundary vectors in the same pack |
| **GST Council decisions** (rate changes, late-fee/interest changes, new returns) | GST rules + calendar logic | pack within **5 business days** of the CBIC notification giving the decision legal effect (Council press releases are NOT law — we wait for the notification, §0.6) |
| **CBDT circulars/notifications** (TDS/TCS mechanics, form changes, due-date extensions) | affected rules + due dates | pack within **5 business days** of Gazette/CBDT publication |
| **MoLE / Labour-Code notifications** (state rules notified, gratuity-insurance s.57(1) date, wage-ceiling changes) | payroll rules + the WS1.B4 watch list | pack within **10 business days**; the compliance-calendar watch items (`/api/compliance/watch`) flag the pending items in the meantime |

Every SLA is to a **verified** pack: values enter only per §0.6 (cited primary instrument or
CA-initialled vector) — an unsourceable value ships as a KNOWN STATUTORY GAP, never a guess.

## 2 · What a pack release contains

1. `rules.yaml` — bumped `version` (scheme `YYYY.MM.n`).
2. `MANIFEST.yaml` — same version + `rules_sha256` recomputed over the exact bytes
   (`sha256sum dif/rules/rules.yaml`) + `channel`.
3. `CHANGELOG.md` — one entry naming every changed rule and its statutory basis.
4. The superseded pack + manifest copied to `archive/` (e.g. `rules-2026.07.1.yaml`).
5. Oracle vectors for any changed value (tests/statutory_oracle/vectors/).

CI enforces 1–4 (`test_rule_set_completeness.py`; Rust `load_verified` tests) — a pack whose
bytes, version, or changelog drift does not merge, and Mahsa refuses to boot on it.

## 3 · Integrity & signing

- **Integrity (enforced now):** the loader (`RuleSet::load_verified`, used by both the
  embedded pack and `MAHSA_RULES`) verifies sha256(bytes) and version against the manifest at
  boot and fails loud on any mismatch. This matches the repo's integrity precedent (the audit
  chain and citation anchors are sha256-based; the Ed25519 JWT keys belong to the auth
  provider, not this repo — there is no in-repo signing-key precedent to reuse).
- **Signing (OWNER-STEP, not yet enforced):** to upgrade integrity to authorship proof, the
  owner generates an Ed25519 keypair offline, signs `rules.yaml` on each release
  (`openssl pkeyutl -sign -rawin`), publishes the signature alongside the manifest, and the
  loader gains a `MAHSA_PACK_PUBKEY` check. Until the owner holds keys, claiming "signed"
  would be theatre; sha256 integrity is what is real today.

## 4 · Tenant visibility

- Mahsa `GET /health` → `rules_version` + `rules_channel` (the pack it **actually loaded**).
- App `GET /health` → `rule_pack {version, channel}`, passed through from Mahsa, `null` when
  Mahsa is unreachable (unknown is reported as unknown, never echoed from a stale value).
- HTMX dashboard appbar: `· rules <version>` beside the Mahsa status dot.
- SPA shell footnote: "Rule pack <version>" (`RulePackVersion.tsx`, `/api/health/rulepack`).
- History: `dif/rules/CHANGELOG.md` is the tenant-facing changelog.

## 5 · Staged rollout & rollback

- **Default (current-for-all):** no env set → every tenant is on the embedded `stable` pack.
- **Staging a new pack:** run a second Mahsa sidecar with
  `MAHSA_RULES=<next-pack.yaml> MAHSA_RULES_MANIFEST=<its MANIFEST>` (manifest `channel: next`)
  and point chosen tenants' `MAHSA_URL` at it; the channel is visible on every health surface,
  so a staged tenant can see they are on `next`.
  <!-- ponytail: rollout gate is per-deployment env, not per-tenant DB flag — Mahsa holds one
       pack per process. Upgrade path: multi-pack AppState keyed by org if partner-cohort
       staging ever needs finer grain than a second sidecar. -->
- **Rollback:** point `MAHSA_RULES`/`MAHSA_RULES_MANIFEST` at the archived pair under
  `dif/rules/archive/` and restart — the loader verifies the archived manifest the same way
  (proven by `rollback_previous_pack_loads_verified_and_the_engine_computes_with_it` in Rust
  and `test_archived_previous_pack_verifies_against_its_manifest` in Python).

## 6 · Scope note (honest boundary)

Today's pack covers the **validation rules** (rules + citations + action copy). Statutory
computation constants living in code (`statutory.py`, Rust mirrors) are versioned by release
and locked by the statutory oracle, not by this pack; folding them into pack data is future
work and is NOT claimed by this mechanism.
