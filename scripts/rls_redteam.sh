#!/usr/bin/env bash
# §WS4.1/§WS4.7 — live tenant-isolation proof. Applies the multi-tenant schema to a throwaway
# database and runs the RLS red-team as a NON-superuser role, asserting one org can never reach
# another's rows (read/write/update/fail-closed). Skips cleanly if no Postgres is reachable, so
# it is safe to call from CI that lacks a database. Uses a Postgres docker container by default;
# override with PG_CONTAINER, or set PG_PSQL to a psql command (e.g. "psql -U you -h host").
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/infra/db/multitenant"
DB="ws4_rls_test"
CONTAINER="${PG_CONTAINER:-api-nest-db-1}"
PGUSER="${PGUSER:-maisha}"

if [ -n "${PG_PSQL:-}" ]; then
  ADMIN() { $PG_PSQL -d postgres "$@"; }
  RUN() { $PG_PSQL -d "$DB" -v ON_ERROR_STOP=1 -q -f -; }
elif command -v docker >/dev/null && docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  ADMIN() { docker exec -i "$CONTAINER" psql -U "$PGUSER" -d postgres "$@"; }
  RUN() { docker exec -i "$CONTAINER" psql -U "$PGUSER" -d "$DB" -v ON_ERROR_STOP=1 -q -f -; }
else
  echo "SKIP: no Postgres reachable (set PG_PSQL or run the '$CONTAINER' container)"
  exit 0
fi

ADMIN -c "DROP DATABASE IF EXISTS $DB;" >/dev/null
ADMIN -c "CREATE DATABASE $DB;" >/dev/null
RUN < "$DIR/001_tenancy.sql"
RUN < "$DIR/002_domain_rls.sql"
RUN < "$DIR/rls_redteam.sql"
ADMIN -c "DROP DATABASE IF EXISTS $DB;" >/dev/null
