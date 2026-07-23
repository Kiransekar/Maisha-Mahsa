"""P0-2 — generic preview/commit for the drawer actions (INVARIANT 9: no silent mutation).

Thin JSON wrapper over the SAME ``app.web.actions`` registry the HTMX drawer posts to, so the
SPA and the server-rendered drawer can never drift into two different mutations.

The two-step contract:

* ``POST /api/domains/{d}/actions/{k}/preview`` — validates + normalizes the submitted values,
  DRY-RUNS the real handler on the request session and ROLLS IT BACK (so the validation is the
  service's own, never a re-implementation that could drift), and returns the normalized echo,
  what will be created, any computed badged figures, and a ``preview_token``. Nothing is ever
  committed here — asserted by row-count in the tests.
* ``POST /api/domains/{d}/actions/{k}/commit`` — requires the token. The token is an HMAC over
  (org, domain, key, normalized values) keyed with the server's session secret, so a commit that
  was never previewed — or whose values changed after the preview — is rejected 409 BEFORE the
  handler runs. Stateless by construction: nothing to store, nothing to expire-sweep.
  # ponytail: no token expiry — values are fully re-validated at commit, the token only proves
  # "these exact values were previewed". Add a timestamp inside the MAC if replay-age matters.

RBAC: preview follows the ``api_bulk`` precedent (``read`` — sizing up a write is reading);
commit carries the capability the HTMX flow already requires for these five actions (``write``,
see ``action_submit`` in ``app.main``). None of the five registry actions is a statutory filing,
so ``require_filing`` does not apply; if a filing action is ever added to the registry, its
commit must gate through ``require_filing``, not here.

Every figure in a response is badged via ``mahsa_coverage.badge_state`` — the one §0.4 gate —
never a hardcoded "verified".
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.mahsa_coverage import badge_state
from app.core.money import Paise
from app.core.principal import Principal
from app.core.rbac import Capability
from app.core.rbac_deps import require, resolve_principal
from app.db.session import get_session
from app.web.actions import Action, find_action
from app.web.actions import Field as ActionField
from app.web.api_domains import _figures_for

router = APIRouter(
    prefix="/api", tags=["actions"], dependencies=[Depends(require(Capability.READ))]
)


class PreviewBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class CommitBody(PreviewBody):
    preview_token: str = ""


# ── pure helpers ──────────────────────────────────────────────────────────────────


def _scalar_error(f: ActionField, v: str) -> str | None:
    """The one primitive validator — shared by top-level fields and lines columns."""
    if f.type == "select" and v not in f.options:
        return f"{f.label} must be one of: {', '.join(f.options)}"
    if f.type == "number":
        try:
            Decimal(v)
        except InvalidOperation:
            return f"{f.label} must be a number"
    if f.type == "date":
        try:
            date.fromisoformat(v)
        except ValueError:
            return f"{f.label} must be an ISO date (YYYY-MM-DD)"
    return None


def normalize_values(
    action: Action, raw: dict[str, str]
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Validate + normalize per the action's own field schema. Returns (normalized, errors);
    on any error nothing downstream runs. Unknown keys are dropped — the handler only ever
    sees the declared fields. ``lines`` fields hold a JSON array of rows validated per the
    field's ``columns`` sub-schema and re-serialized CANONICALLY (sorted keys, no spaces) so
    the preview token binds the same bytes regardless of client key order."""
    normalized: dict[str, str] = {}
    errors: list[dict[str, str]] = []

    def err(f_name: str, message: str) -> None:
        errors.append({"field": f_name, "error": message})

    for f in action.fields:
        v = (raw.get(f.name) or "").strip()
        if not v:
            if f.required:
                err(f.name, f"{f.label} is required")
            else:
                normalized[f.name] = ""  # handlers use `d.get(...) or None`
            continue
        if f.type == "lines":
            try:
                rows = json.loads(v)
            except json.JSONDecodeError:
                err(f.name, f"{f.label} must be a JSON array of rows")
                continue
            if (
                not isinstance(rows, list)
                or not rows
                or not all(isinstance(r, dict) for r in rows)
            ):
                err(f.name, f"{f.label} needs at least one row")
                continue
            norm_rows: list[dict[str, str]] = []
            rows_ok = True
            for i, r in enumerate(rows):
                nr: dict[str, str] = {}
                for c in f.columns:
                    cv = str(r.get(c.name) or "").strip()
                    if not cv:
                        if c.required:
                            err(f"{f.name}[{i}].{c.name}", f"{c.label} is required")
                            rows_ok = False
                        else:
                            nr[c.name] = ""
                        continue
                    cell_err = _scalar_error(c, cv)
                    if cell_err:
                        err(f"{f.name}[{i}].{c.name}", cell_err)
                        rows_ok = False
                    else:
                        nr[c.name] = cv
                norm_rows.append(nr)
            if rows_ok:
                normalized[f.name] = json.dumps(norm_rows, sort_keys=True, separators=(",", ":"))
            continue
        scalar_err = _scalar_error(f, v)
        if scalar_err:
            err(f.name, scalar_err)
            continue
        normalized[f.name] = v
    return normalized, errors


def preview_token(org_id: str, domain: str, key: str, normalized: dict[str, str]) -> str:
    """HMAC(session_secret) over the canonical preview identity. A client cannot mint one
    without the server secret, so "commit without preview" is rejected by construction."""
    payload = json.dumps(
        {"org": org_id, "domain": domain, "key": key, "values": normalized},
        sort_keys=True,
        separators=(",", ":"),
    )
    secret = get_settings().session_secret.encode()
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


def computed_figures(action: Action, normalized: dict[str, str]) -> list[dict[str, Any]]:
    """Money entered in rupees is echoed as its EXACT paise (the unit every book write uses),
    badged through the one §0.4 gate — an input echo is not a Mahsa coverage target, so it
    honestly reads ◐, never a fabricated ✓."""
    figs: list[dict[str, Any]] = []
    for f in action.fields:
        v = normalized.get(f.name) or ""
        if f.type == "number" and "₹" in f.label and v:
            p = Paise.from_rupees(v)
            fig_key = f"{action.domain}_{f.name}_paise"
            figs.append(
                {
                    "key": fig_key,
                    "label": f"{f.label} — exact",
                    "value": p.format_inr(),
                    "raw": int(p),
                    "state": badge_state(fig_key),
                }
            )
    return figs


# ── routes ────────────────────────────────────────────────────────────────────────


def _action_or_404(domain: str, key: str) -> Action:
    action = find_action(domain, key)
    if action is None:
        raise HTTPException(status_code=404, detail=f"unknown action '{domain}/{key}'")
    return action


def _validated(action: Action, values: dict[str, str]) -> dict[str, str]:
    normalized, errors = normalize_values(action, values)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": errors, "note": "Nothing was changed."},
        )
    return normalized


@router.post("/domains/{domain}/actions/{key}/preview")
async def action_preview(
    domain: str,
    key: str,
    body: PreviewBody,
    db: Session = Depends(get_session),
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Validate + echo + dry-run. NO mutation: the handler runs on the request session and is
    rolled back unconditionally — the same code path that will commit is the one previewed."""
    action = _action_or_404(domain, key)
    normalized = _validated(action, body.values)
    try:
        result = action.handler(db, normalized)
        db.flush()  # surface constraint violations now, not at commit time
    except (ValueError, KeyError, TypeError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail={"errors": [{"field": "", "error": str(exc) or "Invalid input"}],
                    "note": "Nothing was changed."},
        ) from exc
    db.rollback()  # a preview NEVER mutates — row-count asserted in tests
    # P0-3: a handler may return (message, engine-computed badged figures) — the figures come
    # from the SAME dry-run service call that just ran, so preview and commit cannot drift.
    message, action_figures = result if isinstance(result, tuple) else (result, [])
    return {
        "domain": domain,
        "key": key,
        "committed": False,
        "normalized": normalized,
        "will_create": message,
        "figures": computed_figures(action, normalized) + action_figures,
        "preview_token": preview_token(principal.org_id, domain, key, normalized),
    }


@router.post("/domains/{domain}/actions/{key}/commit")
async def action_commit(
    domain: str,
    key: str,
    body: CommitBody,
    db: Session = Depends(get_session),
    principal: Principal = Depends(require(Capability.WRITE)),
) -> dict[str, Any]:
    """Perform the previewed mutation. The token must match THESE exact values for THIS org —
    a commit without a preview, or with values edited after the preview, is a 409 and writes
    nothing (INVARIANT 9: every write flow is preview → explicit confirm)."""
    action = _action_or_404(domain, key)
    normalized = _validated(action, body.values)
    expected = preview_token(principal.org_id, domain, key, normalized)
    if not hmac.compare_digest(body.preview_token, expected):
        raise HTTPException(
            status_code=409,
            detail=(
                "No matching preview for these exact values — preview first, then confirm. "
                "Nothing was changed."
            ),
        )
    try:
        result = action.handler(db, normalized)
        db.commit()
    except (ValueError, KeyError, TypeError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail={"errors": [{"field": "", "error": str(exc) or "Invalid input"}],
                    "note": "Nothing was changed."},
        ) from exc
    message = result[0] if isinstance(result, tuple) else result
    return {
        "domain": domain,
        "key": key,
        "committed": True,
        "created": message,
        "normalized": normalized,
        # The domain's badged snapshot AFTER the write — same §0.4 machinery as GET /domains/{d},
        # T11-masked for the committer's role (role is a required positional in _figures_for, so
        # this can never silently regress to an unmasked 2-arg call again).
        "after_figures": _figures_for(db, domain, principal.role),
    }
