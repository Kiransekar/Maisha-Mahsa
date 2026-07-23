#!/usr/bin/env bash
# Launch preflight (launch-pack). Checks env completeness, database reachability and Mahsa
# engine presence, then prints a launch checklist. Exit 1 on any missing REQUIRED config.
#
# Usage:
#   scripts/preflight.sh [ENV_FILE]
# ENV_FILE defaults to infra/.env, then api/.env, whichever exists first; variables already in
# the environment win over the file (so `MAISHA_X=y scripts/preflight.sh` works).
#
# What counts as REQUIRED tracks the code, not opinion:
#   · app/main.create_app refuses missing Better Auth / default secrets in production;
#   · betterauth.legacy_password_auth_enabled hard-disables password login in production, so
#     MAISHA_BETTER_AUTH_URL is the only way anyone authenticates;
#   · a Postgres MAISHA_DATABASE_URL needs the psycopg2 driver (api[pg] extra).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ---- env file ----------------------------------------------------------------------------------
ENV_FILE="${1:-}"
if [ -z "$ENV_FILE" ]; then
  for f in "$ROOT/infra/.env" "$ROOT/api/.env"; do
    [ -f "$f" ] && ENV_FILE="$f" && break
  done
fi
if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
  # File fills gaps only — the live environment wins (mirrors docker compose env_file semantics).
  while IFS='=' read -r k v; do
    case "$k" in ''|\#*) continue ;; esac
    k="$(echo "$k" | tr -d '[:space:]')"
    # strip a trailing inline comment and surrounding whitespace from the value
    v="${v%%#*}"; v="$(echo "$v" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -z "${!k:-}" ] && export "$k=$v"
  done < "$ENV_FILE"
  echo "env file: $ENV_FILE"
else
  echo "env file: (none — checking the live environment only)"
fi

# ---- result accounting -------------------------------------------------------------------------
FAILED=0
declare -a LINES=()
ok()   { LINES+=("  [ok]   $1"); }
warn() { LINES+=("  [warn] $1"); }
fail() { LINES+=("  [FAIL] $1"); FAILED=1; }

ENVIRONMENT="${MAISHA_ENVIRONMENT:-development}"
PROD=0; [ "$ENVIRONMENT" = "production" ] && PROD=1
# In dev, a would-be production failure is a warning; the checklist still prints it.
req() { if [ "$PROD" -eq 1 ]; then fail "$1"; else warn "$1 (required in production)"; fi; }

echo "mode: MAISHA_ENVIRONMENT=$ENVIRONMENT"
echo

# ---- 1. secrets (the app itself refuses these defaults in production) --------------------------
# P2-6: the legacy password login (MAISHA_APP_PASSWORD) is deleted; the session secret now only
# signs action preview tokens — still refused at its shipped default in production.
if [ "${MAISHA_SESSION_SECRET:-dev-insecure-session-secret-change-me}" = "dev-insecure-session-secret-change-me" ]; then
  req "MAISHA_SESSION_SECRET is the shipped default — the app refuses to boot in production"
else ok "MAISHA_SESSION_SECRET set (non-default)"; fi

# ---- 2. auth layer -----------------------------------------------------------------------------
if [ -n "${MAISHA_BETTER_AUTH_URL:-}" ]; then
  ok "MAISHA_BETTER_AUTH_URL=$MAISHA_BETTER_AUTH_URL"
else
  req "MAISHA_BETTER_AUTH_URL unset — auth is Better Auth JWT ONLY (the password login is deleted), so nobody could authenticate; the app refuses to boot in production"
fi
[ -n "${MAISHA_BETTER_AUTH_MFA_CLAIM:-}" ] \
  && ok "MFA claim enforced: ${MAISHA_BETTER_AUTH_MFA_CLAIM}" \
  || warn "MAISHA_BETTER_AUTH_MFA_CLAIM unset — API does not enforce MFA (set only once Better Auth emits the claim)"

# ---- 3. database -------------------------------------------------------------------------------
DB_URL="${MAISHA_DATABASE_URL:-sqlite:///./data/maisha.db}"
PYBIN="$ROOT/api/.venv/bin/python"; [ -x "$PYBIN" ] || PYBIN="$(command -v python3 || true)"
case "$DB_URL" in
  postgres*)
    ok "MAISHA_DATABASE_URL is Postgres"
    case "$DB_URL" in
      *search_path*tenant_core*) ok "URL carries search_path=tenant_core (multi-tenant schema)" ;;
      *) warn "Postgres URL without ?options=-csearch_path%3Dtenant_core,public — multi-tenant tables live in tenant_core (see docs/DEPLOYMENT.md §2)" ;;
    esac
    case "$DB_URL" in
      *:6543*) warn "port 6543 looks like the Supabase TRANSACTION pooler — RLS org binding needs a SESSION-mode connection (port 5432)" ;;
    esac
    if [ -n "$PYBIN" ] && ! "$PYBIN" -c "import psycopg2" 2>/dev/null; then
      fail "psycopg2 not importable by $PYBIN — install with: pip install -e \"api[pg]\""
    fi
    ;;
  sqlite*)
    if [ "$PROD" -eq 1 ]; then warn "MAISHA_DATABASE_URL is SQLite in production (valid for the single-VPS stack; Postgres/Supabase is the multi-tenant path)"
    else ok "MAISHA_DATABASE_URL is SQLite (dev default)"; fi
    ;;
  *) fail "MAISHA_DATABASE_URL has an unrecognised scheme: $DB_URL" ;;
esac
case "$DB_URL" in
  sqlite://|sqlite:///:memory:) ok "in-memory SQLite (tests)" ;;
  sqlite:*)
    # File check only — connecting would CREATE the file as a side effect. Relative paths are
    # relative to api/ (the app's working directory).
    DB_PATH="${DB_URL#sqlite:///}"
    case "$DB_PATH" in /*) : ;; *) DB_PATH="$ROOT/api/$DB_PATH" ;; esac
    if [ -f "$DB_PATH" ]; then ok "SQLite database file exists: $DB_PATH"
    else warn "SQLite file not created yet ($DB_PATH) — the app creates it on first boot / 'make migrate'"; fi
    ;;
  *)
    if [ -n "$PYBIN" ] && "$PYBIN" -c "import sqlalchemy" 2>/dev/null; then
      if OUT="$("$PYBIN" - "$DB_URL" <<'EOF' 2>&1
import sys
from sqlalchemy import create_engine, text
e = create_engine(sys.argv[1], connect_args={"connect_timeout": 5})
with e.connect() as c:
    c.execute(text("SELECT 1"))
print("reachable")
EOF
      )"; then
        ok "database reachable (SELECT 1)"
      else
        if [ "$PROD" -eq 1 ]; then fail "database NOT reachable: $(echo "$OUT" | tail -1)"
        else warn "database not reachable from here: $(echo "$OUT" | tail -1)"; fi
      fi
    else
      warn "sqlalchemy not importable ($PYBIN) — DB reachability not checked; run 'make venv' first"
    fi
    ;;
esac

# ---- 4. Mahsa engine (§0.4 — no ✓ Verified without it) -----------------------------------------
MAHSA_URL="${MAISHA_MAHSA_URL:-http://127.0.0.1:8088}"
if curl -sf --max-time 3 "$MAHSA_URL/health" >/dev/null 2>&1; then
  ok "Mahsa engine healthy at $MAHSA_URL"
elif [ -x "$ROOT/dif/target/release/mahsa" ] || [ -x "$ROOT/dif/target/debug/mahsa" ]; then
  warn "Mahsa binary built (dif/target/…/mahsa) but not answering at $MAHSA_URL — start it (or the docker 'dif' service)"
else
  if [ "$PROD" -eq 1 ]; then
    fail "No Mahsa engine: $MAHSA_URL/health unreachable and no binary in dif/target/ — build with 'cd dif && cargo build --release'"
  else
    warn "No Mahsa engine reachable or built — integration tests will skip; 'cd dif && cargo build'"
  fi
fi

# ---- 5. email + reverse proxy + frontend -------------------------------------------------------
if [ -n "${MAISHA_SMTP_HOST:-}" ] && [ "${MAISHA_SMTP_HOST:-}" != "127.0.0.1" ]; then
  ok "SMTP relay: ${MAISHA_SMTP_HOST}:${MAISHA_SMTP_PORT:-1025}"
else
  warn "MAISHA_SMTP_HOST unset/local — CFO brief, dunning and statutory alerts need a real relay in production"
fi
[ -n "${MAISHA_CFO_EMAIL:-}" ] && ok "MAISHA_CFO_EMAIL=${MAISHA_CFO_EMAIL}" \
  || warn "MAISHA_CFO_EMAIL unset — brief/alerts go to the dev default"
[ -n "${MAISHA_DOMAIN:-}" ] && ok "MAISHA_DOMAIN=${MAISHA_DOMAIN}" \
  || warn "MAISHA_DOMAIN unset — required only for the Caddy (docker-compose.prod.yml) stack"
if [ -f "$ROOT/frontend/.env.production" ] || [ -f "$ROOT/frontend/.env.local" ]; then
  ok "frontend env file present (VITE_API_BASE / VITE_BETTER_AUTH_URL are baked at build time)"
else
  warn "no frontend/.env.production — SPA build will use same-origin defaults (fine only behind one domain)"
fi

# ---- checklist ---------------------------------------------------------------------------------
echo "LAUNCH CHECKLIST"
printf '%s\n' "${LINES[@]}"
echo
echo "Runbook: docs/DEPLOYMENT.md   ·   Post-deploy smoke: make ci && scripts/rls_redteam.sh"
if [ "$FAILED" -eq 1 ]; then
  echo "PREFLIGHT: FAIL — fix the [FAIL] lines above before launch."
  exit 1
fi
echo "PREFLIGHT: OK (warnings above are advisory)"
