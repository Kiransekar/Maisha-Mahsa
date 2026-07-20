#!/usr/bin/env bash
# QG (§WS7.1) grep-gate: all money renders through the ONE canonical Indian lakh/crore
# renderer — app/core/money.py::Paise.format_inr, re-exposed by app/web/format.py
# (inr / inr_rupees) and the "rupees" Jinja filter. A surface that formats money by hand
# loses the ₹NN,NN,NNN.NN grouping and, worse, can drift from the Mahsa-recomputed figure.
#
# RULE (concrete, checkable) — the gate FAILS if any surface does:
#   (a) JS  .toLocaleString(...)  anywhere in app/web  — that is locale grouping, NOT the
#       Indian util (default gives Western 12,34,567 → 1,234,567).
#   (b) a template glues the ₹ glyph directly onto a Jinja expression:  ₹{{ ... }}  — money
#       arrives already formatted (₹ included) from |rupees; a template never assembles it.
#   (c) a template uses Western grouped/fixed money formatting in a Jinja money expression
#       (:,.2f / :, ) — the money spec is Indian grouping, applied in Python, not the template.
#   (d) Python builds an f-string  "...₹{value}..."  outside the canonical renderers.
#
# The two canonical renderers (money.py, web/format.py) legitimately contain "₹{" and are
# excluded. KNOWN pre-existing debt outside WS7.1's scope is baselined below so this gate is
# green on introduction (a lint that ships red gets disabled): the ratchet catches every NEW
# violation. Remove a baseline entry when its owner fixes the surface.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/api/app"
fail=0

emit() { echo "FAIL: $1" >&2; echo "$2" >&2; fail=1; }

# (a) toLocaleString anywhere in the web layer
hits="$(grep -rn 'toLocaleString' "$APP/web" 2>/dev/null || true)"
[ -n "$hits" ] && emit "toLocaleString bypasses the Indian lakh/crore renderer (use |rupees):" "$hits"

# (b) ₹ glued to a Jinja expression in a template
hits="$(grep -rnE '₹[[:space:]]*\{\{' "$APP/web/templates" 2>/dev/null || true)"
[ -n "$hits" ] && emit "hand-assembled money in a template — use the |rupees filter (₹ is included):" "$hits"

# (c) Western grouped/fixed money formatting inside a Jinja money expression in a template
hits="$(grep -rnE '\{\{[^}]*:,[.0-9]*f?[^}]*\}\}' "$APP/web/templates" 2>/dev/null | grep -F '₹' || true)"
[ -n "$hits" ] && emit "Western money grouping in a template — grouping belongs in Python (|rupees):" "$hits"

# (d) f-string ₹{...} in Python outside the canonical renderers (+ named pre-existing debt)
hits="$(grep -rnE '₹\{' "$APP" --include='*.py' 2>/dev/null \
        | grep -vE '/core/money\.py:|/web/format\.py:' \
        | grep -vE '/domains/gst/eway\.py:|/web/actions\.py:' \
        || true)"
[ -n "$hits" ] && emit "hand-formatted ₹ in Python — route through app.web.format.inr / Paise.format_inr:" "$hits"

if [ "$fail" -eq 0 ]; then
  echo "OK: all money routes through the canonical Indian lakh/crore renderer"
else
  exit 1
fi
