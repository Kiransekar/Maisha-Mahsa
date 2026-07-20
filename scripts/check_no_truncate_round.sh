#!/usr/bin/env bash
# QG.3 / §WS1.C3 grep-gate: the truncate-then-round anti-pattern.
# int(Decimal(...) * ...) truncates the fractional remainder of a money product; if that feeds a
# rupee round the remainder is silently dropped (the proven ESI defect). Keep the Decimal exact
# and round explicitly (quantize / to_integral_value), never int() a raw product.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

hits="$(grep -rnE 'int\(\s*Decimal\(' "$ROOT/api/app" --include='*.py' || true)"
if [ -n "$hits" ]; then
  echo "FAIL: truncate-then-round anti-pattern — round on the exact Decimal, do not int() first:" >&2
  echo "$hits" >&2
  exit 1
fi
echo "OK: no truncate-then-round anti-pattern in api/app"
