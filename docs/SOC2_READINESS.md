# SOC 2 Type I Readiness — control mapping + 12-month backlog (§WS10.5)

Status doc, not an attestation. Maps the AICPA Trust Services Criteria (Security / Common
Criteria, the Type I baseline) to controls that **already exist in this repo** (file references
inline — same discipline as DEPLOYMENT.md: nothing aspirational in the "exists" column), then
lists the gap backlog on a 12-month clock toward a Type I examination. Availability,
Confidentiality, Processing Integrity, Privacy criteria can be scoped in later; Security is the
mandatory set.

## Control mapping — what exists today

| TSC | Criterion (abbrev.) | Existing control | Evidence in repo |
|---|---|---|---|
| CC1/CC5 | Control environment & policies | Immutable program spec + governance (§0), build doctrine, append-only progress log | `docs/MASTER_PLAN.md` (444), `CLAUDE.md`, `PROGRESS.md` |
| CC2 | Communication | Deployment runbook w/ OWNER-STEPs; user guide; enterprise-readiness ledger | `docs/DEPLOYMENT.md`, `USER_GUIDE.md`, `docs/ENTERPRISE_READINESS.md` |
| CC3/CC4 | Risk assessment & monitoring | Production audit (~50 findings fixed + verified); CI 19-step binary gate on every merge; grep-gates | `SECURITY_REVIEW.md`, `scripts/ci_gate.sh`, §14 QG.1–4 |
| CC6.1 | Logical access — authn | Single JWT auth system (Better Auth issue, JWKS verify), deny-by-default middleware on every route | `api/app/core/betterauth.py`, `api/app/main.py` `_authenticate` |
| CC6.1 | Logical access — authz | RBAC capability gates on every router; entitlement matrix; MFA (TOTP) in the auth layer | `api/app/core/rbac.py`, `rbac_deps.py`, `entitlements.py` |
| CC6.1 | Tenant isolation | org_id from verified JWT only (never request body); Postgres RLS on every table in the same migration; live RLS red-team suite | `infra/db/multitenant/*.sql`, `rls_redteam.sql`, §0.8 |
| CC6.6/6.7 | Boundaries & transmission | Only Caddy exposes ports (TLS); api/dif internal-only; secrets env-only with prod boot-refusal of defaults | `infra/docker-compose.prod.yml`, `infra/Caddyfile`, `api/app/main.py` |
| CC7.1 | Integrity monitoring | **Hash-chained audit log** (`this_hash = sha256(prev_hash ‖ entry)`), `/audit/verify`; every figure recomputed by an independent engine before display (§0.4) — a control most SaaS cannot show | `api/app/core/audit.py`, `audit_store.py`, `dif/` |
| CC7.2/7.3 | Incident detection & response | Severity-event alerting hook (webhook push); 6-hour CERT-In report template; personal-data breach runbook | `api/app/core/alerting.py`, `docs/legal/CERTIN_INCIDENT_REPORT_TEMPLATE.md`, `BREACH_RUNBOOK_DRAFT.md` |
| CC7.2 | Logging | journald log pipeline with 180-day host retention; NTP-sync enforced at deploy | `infra/host/journald-maisha.conf`, `infra/deploy.sh` |
| CC8.1 | Change management | Immutable spec + ticket IDs in commits; CI gate blocks merge (tests, lint, type-check, RLS drift, oracle); CODEOWNERS on the spec | `docs/MASTER_PLAN.md` §0.3/§0.5, `scripts/ci_gate.sh` |
| CC9.2 | Vendor management | DPA draft with sub-processor annex (Supabase, LLM, email) + change-notice clause | `docs/legal/DPA_DRAFT.md` §3–4 |
| A1.2 (Avail.) | Backup & recovery | restic snapshot backups + restore drill script (never restores over live) | `infra/backup/{backup,restore}.sh`, `restic.cron` |
| P-series (Privacy) | Data-subject rights | DPDP rights workflow (access/correct/erase, 90-day SLA), legal-hold vs 8-year books retention, versioned-notice acceptance log | `api/app/core/dpdp.py`, `legal.py` |

## Gap backlog — 12 months to a Type I

Quarters are from first paying-customer onboarding (P3/P4). A Type I attests design at a point
in time, so the doc/process gaps dominate; most engineering controls above already exist.

**Q1 — formalise what exists (docs, no code)**
- Written Information Security Policy set (access, change-mgmt, incident, vendor, data
  classification) — largely transcription of CLAUDE.md/MASTER_PLAN §0.8 into policy form.
- Risk register with owners + review cadence (seed from SECURITY_REVIEW.md findings).
- Asset inventory (the DEPLOYMENT.md "moving parts" table, formalised + kept current).

**Q2 — process controls with evidence trails**
- Access-review cadence (quarterly review of org users/roles; evidence = review artifacts).
- Vendor review: finalise DPA sub-processor annex `TODO(counsel)` items; collect SOC 2/ISO
  reports from Supabase + LLM + SMTP providers.
- Incident-response tabletop (the §WS10.2 drill) — run it, keep the artifact.
- Onboarding/offboarding checklist for staff with system access.

**Q3 — close engineering gaps (tracked in ENTERPRISE_READINESS.md roadmap)**
- Field-level encryption for sensitive columns (tranche 4; blind-index nuance documented).
- Secrets manager integration (env-only today).
- Vulnerability-management SLA: dependency-audit CI gate exists; add patch-window policy.
- Pen test (WS10.3, Human) — remediation evidence feeds the audit.

**Q4 — audit readiness**
- Select auditor; scope Type I (Security, + Availability if desired).
- Gap assessment against this mapping; remediate; schedule the examination.
- Decide Type II observation window start (Type II = same controls, operating over 3–12
  months; the audit chain + CI gate give unusually strong operating evidence for free).

## Why the audit chain matters here

Most startups assemble screenshots to prove controls operated. Maisha-Mahsa's hash-chained
audit log is itself a tamper-evident record of decisions, approvals, and recomputations —
CC7.1/CC8.1 operating evidence generated as a by-product of the product's own Golden Rule.
Surface this to the auditor early; it shortens the evidence-collection phase materially.
