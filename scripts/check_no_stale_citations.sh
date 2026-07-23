#!/usr/bin/env bash
# §WS1.B4 grep-gate: no repealed-labour-Act-only citations.
#
# The Labour Codes are in force (regime 21-11-2025): Code on Wages 2019 s.69(1) repealed the
# Payment of Wages Act 1936 / Payment of Bonus Act 1965 (and others); Code on Social Security
# 2020 s.164(1) repealed the ESI Act 1948 / EPF & MP Act 1952 / Payment of Gratuity Act 1972.
# A repealed Act may still appear in a citation — but ONLY alongside its successor Code, either
# as an "(ex ...)" trace or via the savings clauses (CoSS s.164(2), CoW s.69(2)). A line citing
# a repealed Act with no Code successor on it is a stale citation: exactly the two-repealed-
# regimes failure this program was born from. Extend REPEALED for WS1.A2 (1961->2025) when that
# sweep lands.
#
# Test dirs are excluded: oracle vectors and tests legitimately quote repealed-Act instruments
# with full provenance prose (saved instruments, SC case law under predecessor Acts).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

REPEALED='EPF & MP Act|Employees. Provident Funds and Miscellaneous|ESI Act|Employees. State Insurance Act|Payment of Bonus Act|Payment of Gratuity Act|Payment of Wages Act'
# A line is fine when the successor Code (or an explicit ex-/savings trace to it) is on the
# line, or when it references the ARCHIVED pre-sweep pack (whose old citations are the point).
ALLOWED='Code on Wages|Code on Social Security|CoSS|ex EPF|ex ESI|ex Payment|archive'

hits="$(grep -rnE "$REPEALED" \
  "$ROOT/dif/rules" "$ROOT/dif/src" "$ROOT/api/app" "$ROOT/frontend/src" \
  --include='*.py' --include='*.rs' --include='*.yaml' --include='*.yml' \
  --include='*.html' --include='*.ts' --include='*.tsx' \
  --exclude-dir=archive \
  | grep -vE "$ALLOWED" || true)"

if [ -n "$hits" ]; then
  echo "FAIL: repealed labour Act cited without its successor Code on the same line" >&2
  echo "      (convention: 'Code on Social Security 2020 s.X (ex EPF & MP Act 1952 s.Y)'):" >&2
  echo "$hits" >&2
  exit 1
fi
echo "OK: no repealed-Act-only labour citations in dif/rules, dif/src, api/app, frontend/src"
