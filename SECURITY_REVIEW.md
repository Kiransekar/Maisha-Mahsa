# Maisha-Mahsa — Security Review (P6-SECREVIEW)

Manual security review of the full application surface before internet exposure, 2026-06-26.
Scope: authentication/session, input handling/uploads, injection, secrets, error handling,
transport, the LLM path, and the audit chain. **No high/critical findings open.** Medium and
low findings are triaged below with rationale and the upgrade path.

## Summary

| Area | Status | Notes |
|---|---|---|
| SQL injection | ✅ none | All DB access is SQLAlchemy ORM/Core (parameterised). The only raw SQL is a static `SELECT 1` liveness probe — no user input concatenated anywhere. |
| Authentication | ✅ sound | Single-user password via constant-time `hmac.compare_digest`; HMAC-signed session cookie (`httponly`, `samesite=lax`, `secure` configurable); production refuses the default password/session-secret. |
| Secrets in VCS | ✅ none | `.env`, `infra/.env`, `*.db`, `/data/` are gitignored; only `.env.example` is committed; `git ls-files` shows no `.env`/DB tracked. |
| Error handling | ✅ no leak | Global exception handler logs the trace server-side and returns a generic message; stack traces never reach the client. |
| Upload safety | ✅ bounded | 10 MB request-body limit (`MAX_BODY_BYTES`); vault paths are content-hash derived (`vault/<sha256>`) — no user-controlled path, no traversal. |
| Transport | ✅ (deploy) | TLS terminated by Caddy; set `MAISHA_SECURE_COOKIES=true` in production (documented in RUNBOOK §2). |
| LLM path | ✅ guarded | Cloud LLM is opt-in (`MAISHA_LLM_PROVIDER`); PII redaction + prompt-injection guardrails run before any cloud call; every number is still recomputed by Mahsa. |
| Audit chain | ✅ verified | SHA-256 hash chain; `GET /audit/verify` + daily job + dashboard banner detect tampering. |

## Findings (triaged)

### M1 — No rate limiting on `/login` (medium, accepted)
Brute-force throttling is not implemented. **Mitigation:** single-user app behind TLS with a
strong operator-set `MAISHA_APP_PASSWORD`; constant-time comparison removes a timing oracle.
**Upgrade path:** add per-IP login throttling (or fail2ban on the access log) before exposing to
a hostile network. Accepted for v1 single-tenant deployment.

### M2 — Session token has no server-side revocation (medium, accepted)
The signed cookie is a static `HMAC(secret, "authed")` with a 2-week `max_age`; there is no
per-session id to revoke individually. **Mitigation:** rotating `MAISHA_SESSION_SECRET`
invalidates all sessions immediately (documented). **Upgrade path:** per-session nonce + a small
session store if multi-device revocation is ever needed. Acceptable for one operator.

### L1 — No CSRF tokens on state-changing POSTs (low, mitigated)
State-changing requests rely on `SameSite=Lax`, which blocks cross-site cookie-bearing POSTs.
**Upgrade path:** add a CSRF token (e.g. double-submit) if the app is ever embedded or shares an
origin with untrusted content. Low risk for a self-hosted single-user dashboard.

### L2 — Body-size limit trusts `Content-Length` (low, mitigated)
The 10 MB guard reads the declared `Content-Length`. A client could omit/understate it, but
Starlette still buffers the body and ASGI server limits apply; OCR/upload handlers read bounded
files. **Upgrade path:** enforce a hard streaming cap at the ASGI/Caddy layer in production.

## Verification

- `make verify` green (Rust + Python tests + ruff + mypy + clippy).
- Hardening behaviours covered by `tests/integration/test_hardening.py` (413 on oversize,
  dependency-aware `/health`, friendly 404, `/audit/verify`).
- Auth behaviours covered by `tests/integration/test_auth.py`.

**Conclusion:** no high/critical issues; M1/M2/L1/L2 accepted for a single-tenant, TLS-fronted,
self-hosted deployment. Re-run this review (and `/security-review`) before any move to
multi-tenant or public multi-user exposure.
