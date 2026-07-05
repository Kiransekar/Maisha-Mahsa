# Enterprise Readiness

Status of Maisha-Mahsa (api-nest) against enterprise-grade criteria. Updated as tranches land.

## Already enterprise-strength (was strong before this effort)

- **Financial correctness** — integer-paise math (BIGINT), deterministic Rust validation engine, statutory citations on every rule.
- **Auditability** — hash-chained, tamper-evident audit log; the Golden Rule (no LLM-fabricated numbers); memory + tax-optimizer decisions sealed too; **now stamped with the acting user**.
- **Testing & gates** — 157 TS + 57 Rust + Python tests; CI runs build + `tsc` + test + migrate-against-real-Postgres + dependency audit.
- **Security baseline** (post prod-audit) — prod-secret boot refusal, security headers, upload limits, DB transactions, FK indexes, fail-loud, non-root Docker.

## Shipped in the enterprise hardening effort

| Tranche | What | Commit |
|---|---|---|
| **1 — Auth** | Multi-user accounts, RBAC (admin/operator/viewer), scrypt hashing, **MFA (RFC-6238 TOTP)**, per-user sessions + per-user audit, admin user management, bootstrap admin | `b60d0f2` |
| **2 — Observability** | Correlation IDs (`x-request-id`), structured JSON access logs, **Prometheus `/metrics`**, liveness/readiness split, graceful shutdown | `e62e371` |
| **3 — Ops** | CORS allowlist, dependency-scan CI gate (block critical, report high) | `bc5ac7c` |

All via `node:crypto` and stdlib — **no new runtime dependency** across the three tranches.

## Remaining roadmap (by value; infra-dependence noted)

### 4 — Data protection (buildable; one nuance)
- **Field-level encryption** (AES-256-GCM transformer, key from env/KMS) for sensitive columns.
  - *Nuance:* `company.pan` / `gstin` are **UNIQUE and looked-up** — non-deterministic GCM breaks
    uniqueness + equality search. These need a **blind index** (HMAC column for lookup) alongside the
    ciphertext, or deterministic encryption. Non-indexed fields (bank_account, ifsc, address) are a
    straight GCM transformer. Don't naively encrypt the unique columns.
- **DPDP Act erasure/export** — a data-subject endpoint (by email/PAN) that exports or crypto-erases
  (redacts) PII across employees/vendors/customers, sealed to the audit chain. Admin-only.
- **Secrets** — env today; integrate a secrets manager (Vault/AWS SM/GCP SM) — *infra-dependent*.

### 5 — Multi-tenancy (large migration)
- Add `company_id` to every domain table + a tenant guard that scopes all queries (row-level
  isolation). Touches all 12 domains and every query/test — a dedicated migration, not a quick slice.
- *Alternative:* one-deployment-per-customer keeps single-tenant acceptable and skips this.

### 6 — HA / horizontal scale (mostly infra-dependent)
- **Rate-limit + login-throttle** → shared store (**Redis**) instead of in-memory.
- **Scheduler** → single-fire across instances via a DB advisory lock (Postgres) or leader election.
- Audit-append is already cross-instance-safe (the `UNIQUE(prev_hash)` index fails a forked write loud).

### 7 — Enterprise SSO (infra-dependent)
- OIDC/SAML (Okta/Azure AD/Google Workspace) + SCIM provisioning — needs a live IdP; the RBAC and
  session layer from Tranche 1 is the foundation to plug it into.

## Tracked debt
- 4 high npm advisories fixable only via a breaking `@nestjs/typeorm@11` bump — deferred, gated as
  report-only in CI (critical is blocking).
- No ESLint gate yet (advisory from the prod audit) — a separate cleanup pass.
