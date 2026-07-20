#!/usr/bin/env bash
# §0.8 / QG.3 gate: every tenant-scoped table in the multi-tenant schema ships with row-level
# security AND a policy in the same migration, or CI fails. Static check (no DB needed) so it
# runs everywhere; the live isolation proof is scripts/rls_redteam.sh.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/infra/db/multitenant"

# Intentionally global (cross-org) tables — a global identity, not tenant data. Keep this list
# tiny and justified; anything else MUST be tenant-scoped.
ALLOW=" app_users "

[ -d "$DIR" ] || { echo "OK: no multi-tenant schema yet ($DIR absent)"; exit 0; }

tables="$(grep -hoiE 'CREATE TABLE [a-z_]+' "$DIR"/*.sql | awk '{print $3}' | sort -u)"
fail=0
count=0
for t in $tables; do
  case "$ALLOW" in *" $t "*) continue ;; esac
  count=$((count + 1))
  if ! grep -qiE "ALTER TABLE $t\b.*ENABLE ROW LEVEL SECURITY" "$DIR"/*.sql; then
    echo "FAIL: table '$t' is missing ENABLE ROW LEVEL SECURITY (§0.8)" >&2
    fail=1
  fi
  if ! grep -qiE "CREATE POLICY [a-z_]+ ON $t\b" "$DIR"/*.sql; then
    echo "FAIL: table '$t' has no RLS policy (§0.8)" >&2
    fail=1
  fi
done

if [ "$fail" -ne 0 ]; then
  echo "RLS coverage gate FAILED — a tenant table without RLS can leak across orgs." >&2
  exit 1
fi
echo "OK: all $count tenant tables have RLS enabled + a policy (§0.8)"
