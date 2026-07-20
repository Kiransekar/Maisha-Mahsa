#!/usr/bin/env bash
# WS9.3 grep-gate: every locally-generated IRN / e-invoice surface must carry the
# draft-honesty label, because a self-computed IRN is never IRP-registered and has no
# legal force as an e-invoice until the real IRP call happens.
#
# RULE (concrete, checkable): an "IRN-emitting surface" is any non-test *.py file under
# api/app that computes or renders a locally-generated IRN / e-invoice, detected as a file
# containing any of:
#   - a call to compute_irn(              (the NIC-algorithm IRN generator)
#   - the literal payload key  "Irn":     (the NIC e-invoice schema field)
#   - the literal payload key  "QrData"   (the IRP-signed-QR data block)
# Any file matching one of the above MUST also carry the exact draft label, either by
# importing/referencing the DRAFT_IRN_LABEL constant (app.domains.gst.gst_calc), or by
# containing the literal string:
#   "DRAFT — not IRP-registered; not a valid e-invoice until registered"
# This covers today's JSON payload surface and any future PDF renderer or QR-caption code
# that pulls in the same IRN/QrData fields — the gate fails and lists every offending file
# if neither the import nor the literal label string is present in it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/api/app"
LABEL='DRAFT — not IRP-registered; not a valid e-invoice until registered'

surfaces="$(grep -rlE 'compute_irn\(|"Irn":|"QrData"' "$APP" --include='*.py' 2>/dev/null || true)"

fail=0
for f in $surfaces; do
  if ! grep -qF "DRAFT_IRN_LABEL" "$f" && ! grep -qF "$LABEL" "$f"; then
    echo "FAIL: $f emits an IRN/e-invoice surface without the draft-honesty label" >&2
    fail=1
  fi
done

if [ -z "$surfaces" ]; then
  echo "OK: no IRN-emitting surface found in api/app (gate is a no-op tripwire for future code)"
  exit 0
fi

if [ "$fail" -ne 0 ]; then
  exit 1
fi
echo "OK: every IRN-emitting surface carries the draft-honesty label"
