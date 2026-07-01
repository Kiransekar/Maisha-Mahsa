# Maisha API — NestJS

Enterprise NestJS port of the FastAPI suite in `../api`. All 12 domains, verified against the
Python reference. The Rust **Mahsa** gatekeeper (`../dif`) is kept as-is and integrated over HTTP
— every result is folded/validated by Mahsa and sealed into a hash-chained audit log (the Golden Rule).

## Status

**All 12 domains ported, integrated, building & booting green** (109 domain/parity tests + auth/audit/money).

| Layer (Python → Nest) | Location |
|---|---|
| pure paise math (`*_calc.py`) | `src/domains/<d>/<d>.calc.ts` (+ `.spec.ts` locked to Python-captured values) |
| Pydantic schemas | `src/domains/<d>/<d>.dto.ts` (class-validator) |
| SQLAlchemy models | `src/domains/<d>/<d>.entities.ts` (TypeORM; money = BIGINT paise) |
| domain service + `build_snapshot` | `src/domains/<d>/<d>.service.ts` |
| FastAPI router | `src/domains/<d>/<d>.controller.ts` (+ `/fold` via the loop) |
| MahsaClient | `src/mahsa/mahsa.service.ts` |
| hash-chained AuditLog | `src/audit/` |
| the fold loop | `src/core/loop.service.ts` |
| single-user auth | `src/auth/` |
| money (`core/money.py`) | `src/common/money.ts` |

Domains: gst, ledger, treasury, payroll, revenue, expense, payables, forecast, equity, tax,
compliance, vault. 62 routes; OpenAPI at `/docs`.

## Run (local, SQLite)

    npm install
    npm test                 # 112 tests
    npm run start:dev        # http://localhost:8000  (docs at /docs)

Mahsa must be running for `/fold` routes: `cd ../dif && cargo run` (serves :8088). Without it,
`/fold` fails loud (500) — it never fabricates a verdict.

## Run (launch stack: Mahsa + Postgres + API)

    cp .env.example .env      # set strong MAISHA_APP_PASSWORD + MAISHA_SESSION_SECRET
    docker compose up -d --build

Postgres in prod (migrations own the schema, `synchronize` off); SQLite for local/tests.

## Auth

Single-operator, HMAC-signed cookie (mirrors the Python design). `POST /login {password}` sets the
cookie; all `/api/*` routes require it. Public: `/health*`, `/login*`, `/docs*`. Production boot is
refused if the default password/secret are unchanged.

## Migrations

    npm run migration:run     # build + apply
    npm run typeorm migration:generate src/db/migrations/<Name>   # after entity changes

## Deferred (next slices — flagged, not silently skipped)

- **LLM drafting layer** (`../api/app/llm/*`): Ollama/Claude constrained decode, retry/verify,
  guardrails, routing, LlmTrace. The loop is drafting-ready (`LoopService`), generator not wired.
- **Scheduler + email** (`../api/app/jobs.py`, `core/email`): daily capture + CFO brief.
- **File transports**: payslip/Form-16 PDF (payroll), OCR receipt parsing (expense), multipart
  CSV upload (treasury currently takes CSV in the JSON body). A few cross-domain routes noted in
  per-domain `deferred` from the port.
- **Web UI**: intentionally out of scope (API-only). HTMX UI stays on the Python side / separate SPA.
