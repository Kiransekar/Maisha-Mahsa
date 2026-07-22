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

# ------------------------------------------------------------------ React SPA (frontend/src) ---
# §WS7.1 mandates this lint, and until 2026-07-21 it scanned api/app ONLY — while the React SPA
# renders money on every screen and was scanned by NOTHING. The SPA's canonical renderer is
# frontend/src/lib/money.ts (inr / inrOrPending), which wraps Intl.NumberFormat("en-IN"). It is
# the ONLY place allowed to construct a number formatter or to emit the ₹ glyph mechanically;
# everything else calls inr(). Onboarding.tsx::inrPrecise is a legitimate composition — it calls
# inr() and appends the paise remainder — so it trips none of these rules.
SPA="$ROOT/frontend/src"
if [ -d "$SPA" ]; then
  # (e) a second number formatter outside the canonical module — this is how en-IN grouping
  #     drifts to Western 1,234,567 on one screen and not another.
  hits="$(grep -rnE 'toLocaleString|Intl\.NumberFormat' "$SPA" \
            --include='*.ts' --include='*.tsx' 2>/dev/null \
          | grep -vE '/lib/money\.ts:' \
          | grep -vE '/routes/Approvals\.tsx:' \
          || true)"
  [ -n "$hits" ] && emit "SPA formats money outside frontend/src/lib/money.ts (use inr/inrOrPending):" "$hits"

  # (f) the ₹ glyph glued onto a template expression — money arrives already formatted from inr().
  hits="$(grep -rnE '₹[[:space:]]*(\$\{|\{)' "$SPA" \
            --include='*.ts' --include='*.tsx' 2>/dev/null \
          | grep -vE '/lib/money\.ts:' \
          | grep -vE '/routes/Approvals\.tsx:' \
          || true)"
  [ -n "$hits" ] && emit "hand-assembled ₹ in the SPA — use inr() (the ₹ is included):" "$hits"
fi

# BASELINED SPA DEBT (excluded above, remove the exclusion when its owner fixes it):
#   frontend/src/routes/Approvals.tsx:144,149 — a THIRD money renderer: its own
#   Intl.NumberFormat("en-IN") plus a hand-glued `₹${...}.${paise}`. It renders exact paise, which
#   lib/money.ts::inr (whole rupees) does not, so it is not a one-line swap — the fix is to export
#   a paise-exact renderer from lib/money.ts and delete this one. Named here, not silently ignored.

if [ "$fail" -eq 0 ]; then
  echo "OK: all money routes through the canonical Indian lakh/crore renderer (api/app + frontend/src)"
else
  exit 1
fi
