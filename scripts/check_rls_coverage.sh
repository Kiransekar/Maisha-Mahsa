#!/usr/bin/env bash
# §0.8 / QG.3 gate: every tenant-scoped table in EVERY schema path ships with row-level security
# AND a policy in that same schema path, or CI fails. Static check (no DB needed) so it runs
# everywhere; the live isolation proof is scripts/rls_redteam.sh.
#
# THIS REPO HAS TWO SCHEMA PATHS AND BOTH ARE REAL:
#   1. infra/db/multitenant/*.sql   — the reference/red-team schema (scripts/rls_redteam.sh)
#   2. api/alembic/versions/*.py    — THE PRODUCTION PATH. The Makefile's `migrate` target is
#                                     `alembic upgrade head`; that is what creates the schema a
#                                     customer's data actually lands in.
# Before 2026-07-21 this gate globbed only (1). A tenant table added by a migration with no RLS
# policy passed the gate — i.e. the gate FAILED OPEN on the one path that matters most. Each path
# is now checked independently: a table's RLS must live in the SAME path that creates the table,
# because a policy in the .sql files does not protect a table that alembic created.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Intentionally global (cross-org) tables — a global identity, not tenant data. Keep this list
# tiny and justified; anything else MUST be tenant-scoped.
ALLOW=" app_users password_credentials mfa_totp "

fail=0
total=0

# check_path LABEL DIR GLOB — greps CREATE TABLE in DIR/GLOB and requires ENABLE ROW LEVEL
# SECURITY + CREATE POLICY for each non-allowlisted table within that same DIR/GLOB.
check_path() {
  local label="$1" dir="$2" glob="$3"
  if [ ! -d "$dir" ]; then
    echo "OK: $label — no schema at $dir (skipped)"
    return
  fi
  # shellcheck disable=SC2086  # glob must expand
  local files=( $dir/$glob )
  if [ ! -e "${files[0]}" ]; then
    echo "OK: $label — no files matching $glob (skipped)"
    return
  fi

  local tables count=0 bad=0
  tables="$(grep -hoiE 'CREATE TABLE (IF NOT EXISTS )?[a-z_]+' "${files[@]}" \
            | awk '{print $NF}' | sort -u)"
  for t in $tables; do
    case "$ALLOW" in *" $t "*) continue ;; esac
    count=$((count + 1))
    if ! grep -qiE "ALTER TABLE $t\b.*ENABLE ROW LEVEL SECURITY" "${files[@]}"; then
      echo "FAIL[$label]: table '$t' is missing ENABLE ROW LEVEL SECURITY (§0.8)" >&2
      fail=1; bad=1
    fi
    if ! grep -qiE "CREATE POLICY [a-z_]+ ON $t\b" "${files[@]}"; then
      echo "FAIL[$label]: table '$t' has no RLS policy (§0.8)" >&2
      fail=1; bad=1
    fi
  done
  if [ "$bad" -eq 0 ]; then
    echo "OK: $label — all $count tenant tables have RLS enabled + a policy (§0.8)"
  else
    echo "RED: $label — $count tenant tables checked, at least one is unprotected (see FAIL above)"
  fi
  total=$((total + count))
}

check_path "reference schema" "$ROOT/infra/db/multitenant" "*.sql"
check_path "PRODUCTION (alembic)" "$ROOT/api/alembic/versions" "*.py"

if [ "$fail" -ne 0 ]; then
  echo "RLS coverage gate FAILED — a tenant table without RLS can leak across orgs." >&2
  exit 1
fi
echo "OK: $total tenant-table checks passed across both schema paths (§0.8)"
