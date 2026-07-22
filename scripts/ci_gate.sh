#!/usr/bin/env bash
# §WS4.8 — THE gate. `make ci` and .github/workflows/verify.yml both run this file, verbatim,
# and nothing else — that is the whole point: a suite that is green on one machine and red on
# another is a defect, so there must be exactly one place the gate's steps are listed.
#
# Every step below runs even if an earlier one fails (no `set -e`) so a single run always shows
# the full picture — cargo, python and frontend health all at once — and the job fails at the
# end if anything failed. Do NOT add `|| true` to silence a step: a red step here means main is
# actually broken, OR (the statutory_oracle step) that a real, unresolved conflict with the
# statute exists. Both are correct reasons to block a merge.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Same cargo resolution as the Makefile: prefer a rustup install, fall back to PATH.
if [ -x "$HOME/.cargo/bin/cargo" ]; then
  CARGO="$HOME/.cargo/bin/cargo"
else
  CARGO="cargo"
fi

declare -a NAMES=()
declare -a STATUSES=()
declare -a NOTES=()
FAILED=0
SKIPPED_ANY=0

# ================================================================================================
# KNOWN STATUTORY GAPS  (§0.6) — the whole point of this list
# ================================================================================================
# A statutory-oracle vector may be legitimately RED: §0.6 forbids inventing a statutory value, so
# when a figure cannot be traced to a primary instrument the vector stays red until a CA sources
# it. That is a HONEST GAP, not a broken build.
#
# Before 2026-07-21 the gate could not tell the two apart: the oracle step simply failed, the
# workflow said "expected", and a REAL regression landing in that same step would have been read
# as "yeah, the oracle is red, it always is". A permanently-red step is a step nobody reads.
#
# So: list the exact pytest node id of every known gap below, with WHY. The gate then asserts the
# set of failing vectors is EXACTLY this set —
#   · a failure NOT on this list  -> REGRESSION -> the gate goes red
#   · an entry on this list that now PASSES -> STALE -> the gate goes red (delete the entry)
#   · exactly this set            -> PASS, printed under a "KNOWN STATUTORY GAP" label
# The list rots the moment it is allowed to be approximate, hence the stale-entry check.
#
# DO NOT add an entry to silence a failing calculation. This list is only for a vector whose
# EXPECTED VALUE cannot be sourced. Every entry needs a §0.6 reason and an owner-facing next step.
declare -a KNOWN_STATUTORY_GAPS=(
  # (empty 2026-07-22 — the Form 130 gap was closed: the Department's own forms document
  # confirming Form No. 130 / rule 215 / s.395(4) was retrieved via the Internet Archive snapshot
  # of the incometaxindia.gov.in URL and read verbatim; vector regime_form_map_salary_cert_2025
  # is now provenance=primary. Add future entries per the rules above.)
)

# run NAME NOTE -- CMD...    Runs CMD, records PASS/FAIL under NAME, keeps going regardless.
run() {
  local name="$1" note="$2"
  shift 2
  echo
  echo "=== $name ==="
  if "$@"; then
    NAMES+=("$name"); STATUSES+=("PASS"); NOTES+=("")
  else
    NAMES+=("$name"); STATUSES+=("FAIL"); NOTES+=("$note")
    FAILED=1
  fi
}

# ---------------------------------------------------------------- Rust (Mahsa) -----------------
run "cargo build" \
  "" \
  bash -c "cd dif && '$CARGO' build"
# ^ Must run before any Python test step: tests/conftest.py's mahsa_server fixture SKIPS
#   (does not fail) integration tests when dif/target/{debug,release}/mahsa is missing. Building
#   here in CI is the fix for "no loop/integration test can silently skip for want of it."

run "cargo test" "" bash -c "cd dif && '$CARGO' test"
run "cargo clippy" "" bash -c "cd dif && '$CARGO' clippy --all-targets -- -D warnings"

# ---------------------------------------------------------------- Python (Maisha) --------------
if [ ! -x api/.venv/bin/python ]; then
  echo; echo "=== venv (first run) ==="
  make -C "$ROOT" venv
fi
PY="$ROOT/api/.venv/bin"

run "ruff" "" bash -c "cd api && $PY/ruff check ."
run "mypy" "" bash -c "cd api && $PY/mypy app evals"

run "grep-gate: no-truncate-round" "" bash scripts/check_no_truncate_round.sh
run "grep-gate: no-draft-irn" "" bash scripts/check_no_draft_irn.sh
run "grep-gate: money-format" "" bash scripts/check_money_format.sh
run "grep-gate: rls-coverage" "" bash scripts/check_rls_coverage.sh
if [ -f scripts/check_no_stale_citations.sh ]; then
  run "grep-gate: no-stale-citations" "" bash scripts/check_no_stale_citations.sh
fi

run "pytest: unit" "" bash -c "cd api && $PY/pytest tests/unit -q"
run "pytest: integration" "" bash -c "cd api && $PY/pytest tests/integration -q"

# ---- statutory oracle: known gaps vs regressions -----------------------------------------------
# Splits a red oracle run into "a vector we knowingly cannot source (§0.6)" and "something broke".
# See KNOWN_STATUTORY_GAPS at the top of this file for the contract.
oracle_gate() {
  local out rc tmp
  tmp="$(mktemp -d)"
  out="$(cd "$ROOT/api" && "$PY/pytest" tests/statutory_oracle -q --tb=short -rf 2>&1)" && rc=0 || rc=$?
  echo "$out"

  # pytest: 0 = all passed, 1 = tests failed. Anything else (2 usage, 3 internal, 4 usage error,
  # 5 no tests collected) means the oracle did not actually run — never a "known gap".
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; then
    echo
    echo "ORACLE GATE: pytest exited $rc — the oracle did not run (collection error, crash, or no"
    echo "tests collected). That is never a statutory gap. Fix the harness."
    rm -rf "$tmp"; return 1
  fi

  # Node ids out of the `-rf` short summary: "FAILED <nodeid> - <message>".
  printf '%s\n' "$out" | grep '^FAILED ' | sed 's/^FAILED //; s/ - .*$//' | sort -u > "$tmp/actual"
  printf '%s\n' ${KNOWN_STATUTORY_GAPS[@]+"${KNOWN_STATUTORY_GAPS[@]}"} \
    | grep -v '^$' | sort -u > "$tmp/known"

  local regressions stale verdict=0
  regressions="$(comm -23 "$tmp/actual" "$tmp/known")"
  stale="$(comm -13 "$tmp/actual" "$tmp/known")"

  echo
  echo "---- statutory oracle: gap/regression split ----"
  if [ -n "$regressions" ]; then
    echo "REGRESSION — these vectors failed and are NOT known statutory gaps:"
    printf '    %s\n' $regressions
    echo "  A vector that used to reproduce the statute no longer does. This blocks the merge."
    verdict=1
  fi
  if [ -n "$stale" ]; then
    echo "STALE known-gap entry — these are listed as known gaps but now PASS:"
    printf '    %s\n' $stale
    echo "  The gap was closed and nobody deleted the entry. Remove it from KNOWN_STATUTORY_GAPS"
    echo "  in this file, or the list stops meaning anything and a future regression hides behind it."
    verdict=1
  fi
  if [ "$verdict" -eq 0 ]; then
    if [ -s "$tmp/known" ]; then
      echo "KNOWN STATUTORY GAP(S) — red on purpose, §0.6 (no invented statutory value):"
      sed 's/^/    /' "$tmp/known"
      echo "  No regressions. Every other vector reproduces its cited instrument exactly."
    else
      echo "All vectors green; no known statutory gaps outstanding."
    fi
  fi
  echo "-----------------------------------------------"
  rm -rf "$tmp"
  return "$verdict"
}
run "oracle: gaps vs regressions" \
  "a vector failed that is NOT a known §0.6 gap, or a listed gap went green — see the split above" \
  oracle_gate

# ---- E2E (§WS4.8) ------------------------------------------------------------------------------
# The real product loop end to end: real Mahsa binary over HTTP for the fold/validate/unfold/audit
# chain, and real HTTP through the real app (TestClient over app.main.app) for auth + the RBAC
# matrix. These files also run inside "pytest: integration"; the separate step exists because
# §WS4.8 names E2E as its own leg AND because a SKIP is a failure here — an E2E leg that opts out
# proves nothing, and the mahsa_server fixture skips (does not fail) when the binary is missing.
e2e_gate() {
  local out rc
  out="$(cd "$ROOT/api" && "$PY/pytest" \
          tests/integration/test_full_loop.py \
          tests/integration/test_auth_e2e.py \
          tests/integration/test_rbac_matrix.py \
          tests/integration/test_verified_flow.py \
          -q --tb=short -rs 2>&1)" && rc=0 || rc=$?
  echo "$out"
  [ "$rc" -ne 0 ] && return 1
  if printf '%s\n' "$out" | grep -q '^SKIPPED '; then
    echo
    echo "E2E GATE: a test SKIPPED (see SKIPPED above). The E2E leg is the only proof the whole"
    echo "stack works together; a skip here is an untested build, not a pass."
    return 1
  fi
  return 0
}
run "pytest: E2E (real loop + real HTTP)" \
  "the end-to-end product loop is broken, or an E2E test skipped instead of running" \
  e2e_gate

# ---- red team (§WS4.8) -------------------------------------------------------------------------
# scripts/rls_redteam.sh is the ONLY live cross-tenant isolation proof in this repo: it applies the
# schema to a throwaway database and, as a NON-superuser, asserts one org cannot read/write/update
# another's rows. The static gate above (check_rls_coverage.sh) proves a policy EXISTS; only this
# proves the policy WORKS. It needs a live Postgres, so it can skip — and a silent skip on the one
# tenant-isolation proof is exactly the fail-open this round exists to stop. Therefore:
#   · CI (or REQUIRE_REDTEAM=1): a skip is a FAILURE. verify.yml ships a postgres service, so in
#     CI it always runs for real.
#   · a laptop with no Postgres: reported as SKIP — never PASS — with a loud banner at the end.
REDTEAM_SKIPPED=0
redteam_gate() {
  local out rc
  out="$(bash "$ROOT/scripts/rls_redteam.sh" 2>&1)" && rc=0 || rc=$?
  echo "$out"
  [ "$rc" -ne 0 ] && return 1
  if printf '%s\n' "$out" | grep -q '^SKIP:'; then
    if [ "${CI:-}" = "true" ] || [ -n "${REQUIRE_REDTEAM:-}" ]; then
      echo
      echo "REDTEAM GATE: no Postgres was reachable, so the live cross-tenant isolation proof did"
      echo "NOT run — and this is CI (or REQUIRE_REDTEAM is set), where it must. Provide a"
      echo "postgres service (see .github/workflows/verify.yml) or set PG_PSQL."
      return 1
    fi
    REDTEAM_SKIPPED=1
  fi
  return 0
}
run "redteam: live RLS cross-tenant" \
  "one org could reach another org's rows — the isolation policy does not actually hold" \
  redteam_gate
if [ "$REDTEAM_SKIPPED" -eq 1 ]; then
  STATUSES[$((${#STATUSES[@]} - 1))]="SKIP"
  NOTES[$((${#NOTES[@]} - 1))]="NOT RUN: no Postgres reachable. Tenant isolation is UNPROVEN on this run."
  SKIPPED_ANY=1
fi

run "golden eval" "" bash -c "cd api && $PY/python -m evals.harness --all"

# ---------------------------------------------------------------- Frontend ---------------------
run "frontend: npm ci" "" bash -c "cd frontend && npm ci"
run "frontend: tsc -b" "" bash -c "cd frontend && npx tsc -b"
run "frontend: vitest" "" bash -c "cd frontend && npx vitest run"
run "frontend: oxlint" "" bash -c "cd frontend && npx oxlint"

# ---------------------------------------------------------------- Summary ----------------------
echo
echo "==================== CI GATE SUMMARY ===================="
for i in "${!NAMES[@]}"; do
  printf "  %-36s %s\n" "${NAMES[$i]}" "${STATUSES[$i]}"
  if [ -n "${NOTES[$i]}" ]; then
    printf "      -> %s\n" "${NOTES[$i]}"
  fi
done
echo "==========================================================="

if [ "$SKIPPED_ANY" -ne 0 ]; then
  echo
  echo "!!! ONE OR MORE GATES DID NOT RUN (status SKIP above). A SKIP is not a PASS: the property"
  echo "!!! that gate exists to prove is UNPROVEN on this run. In CI these are hard failures."
fi

if [ "$FAILED" -ne 0 ]; then
  echo
  echo "CI GATE: FAILED. See the FAIL rows above — each carries its own error output higher in"
  echo "this log. EVERY red row is a real defect."
  echo
  echo "There is no longer an 'expected red' row. A vector that is deliberately unsourced (§0.6)"
  echo "is listed in KNOWN_STATUTORY_GAPS at the top of this file and the 'oracle: gaps vs"
  echo "regressions' step PASSES on it while printing it under a KNOWN STATUTORY GAP label. That"
  echo "step going red therefore means one of exactly two things, both real: a vector regressed,"
  echo "or a listed gap was closed and its entry was never deleted."
  exit 1
fi
echo
echo "CI GATE: all green."
