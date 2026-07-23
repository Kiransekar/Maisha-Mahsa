"""WS10.1 — DPDP data-principal rights workflow: request tracking, 90-day SLA, legal hold.

DRAFT-FOR-COUNSEL POSTURE (§0.6). This module implements *mechanics* — deadline arithmetic,
state, evidence — and asserts compliance with nothing. The DPDP-notice text itself is
``docs/legal/DPDP_NOTICE_DRAFT.md`` (draft, counsel-gated, same as every other document there);
the breach runbook is ``docs/legal/BREACH_RUNBOOK_DRAFT.md`` (docs-only, owner-executed).

What is deliberately REUSED rather than re-built:

* **SLA surfacing** — a rights request's response deadline is a row in the EXISTING compliance
  calendar (``ComplianceService.add_deadline`` / ``mark_filed``), so it shows up in the same
  calendar, alerts and overdue counts every statutory deadline already does. No parallel
  deadline system.
* **Legal hold** — whether an erasure touches records still under the books-retention duty is
  answered by the vault's retention machinery (``vault_calc.retention_class`` /
  ``is_retention_overdue`` — 8 years from FY-end, §WS1.C5), the single owner of that math.
  A held erasure NEVER silently deletes anything: it cannot even be closed until retention
  lapses, and the statutory basis is recorded on the row and in the audit chain.
* **Processing log** — every lifecycle event is sealed onto the EXISTING hash-chained audit log
  via ``audit_store.append``. The chain is append-only and never pruned, which satisfies the
  ≥1-year processing-log retention by construction.
* **Tenancy** — org comes from :func:`app.core.principal.current_org` (verified JWT, §0.8),
  never a parameter; no bound org → raise (``legal.OrgUnboundError``), same as the acceptance
  log. Postgres RLS (``0010_dpdp_rights``) is the second line of defence.

STATUTORY VALUES (§0.6):

* **90-day SLA** — pinned by MASTER_PLAN §WS10.1 ("90-day SLA tracking"). The precise DPDP
  Rules citation for the response period is BLOCKED-counsel: tracked in
  ``docs/legal/DPDP_NOTICE_DRAFT.md``; the figure here is the program spec's, not an invention.
* **8-year books retention** — Companies Act 2013 s.128(5) ("not less than eight financial
  years"), already sourced in ``api/tests/statutory_oracle/vectors/ws1c_proven_defects.yaml``
  and implemented by the vault (§WS1.C5). This module cites and reuses it; it does not restate
  the number anywhere the vault isn't the source.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit_store
from app.core.legal import OrgUnboundError
from app.core.principal import current_org, current_user
from app.db.models.legal import DpdpRightsRequest
from app.db.models.vault import Document
from app.domains.compliance.service import ComplianceService
from app.domains.vault import vault_calc

#: MASTER_PLAN §WS10.1 — respond to a data-principal rights request within 90 days of receipt.
SLA_DAYS = 90

#: Rules-version stamp for the sealed lifecycle events (same convention as rbac_deps).
RULES_VERSION = "dpdp.2026.1"

REQUEST_TYPES = ("access", "correction", "erasure")

#: The statutory basis recorded when an erasure is held. Companies Act 2013 s.128(5) is quoted
#: in the CA-facing oracle vectors (ws1c_proven_defects.yaml); the retention *window* itself is
#: computed only by the vault (§WS1.C5). DPDP-side carve-out wording is counsel's to settle —
#: see docs/legal/DPDP_NOTICE_DRAFT.md §"Legal hold".
LEGAL_HOLD_BASIS = (
    "Erasure deferred — legal hold: records in scope remain under the statutory "
    "books-of-account retention duty (Companies Act 2013 s.128(5): not less than eight "
    "financial years; retention windows computed by the vault per §WS1.C5). Retained records "
    "are never deleted while the duty runs; the request completes when retention lapses. "
    "See docs/legal/DPDP_NOTICE_DRAFT.md."
)


def sla_due_date(received_date: str) -> str:
    """ISO due date = received + 90 calendar days (MASTER_PLAN §WS10.1). Pure."""
    return (date.fromisoformat(received_date) + timedelta(days=SLA_DAYS)).isoformat()


def _require_org() -> str:
    org = current_org()
    if not org:
        raise OrgUnboundError(
            "no verified org bound to this request; refusing to touch rights requests"
        )
    return org


# ---------------------------------------------------------------------------------------
# Legal hold — the vault's retention machinery is the ONLY oracle for "still retained".
# ---------------------------------------------------------------------------------------


def retained_statutory_documents(session: Session, as_of: str) -> list[Document]:
    """Documents of the statutory retention class (invoices, returns, payslips… — the 8y-from-
    FY-end set) whose retention has NOT lapsed at ``as_of``. Both the class and the lapse test
    come from ``vault_calc`` — this function adds no retention math of its own.

    ponytail: no per-data-principal record linkage exists yet, so the hold is evaluated
    org-wide (any retained statutory record holds any erasure) — conservative in exactly the
    direction the duty requires. Narrow it to principal-linked records when documents carry a
    data-principal reference.
    """
    anchor = date.fromisoformat(as_of)
    return [
        d
        for d in session.scalars(select(Document)).all()
        if vault_calc.retention_class(d.doc_type) == "statutory"
        and not vault_calc.is_retention_overdue(d.retention_until, anchor)
    ]


def erasure_hold(session: Session, as_of: str) -> str | None:
    """The statutory basis for holding an erasure at ``as_of``, or ``None`` when nothing in
    scope is still retained. This is THE load-bearing check: both request creation and request
    closing route through it, so removing it breaks both (mutation-locked in the tests)."""
    if retained_statutory_documents(session, as_of):
        return LEGAL_HOLD_BASIS
    return None


class LegalHoldError(ValueError):
    """An erasure request cannot complete while retained records are in scope. Carries the
    statutory basis as its message. Subclasses ValueError so the web action layer's existing
    422 handling surfaces it verbatim ("Nothing was changed.")."""


# ---------------------------------------------------------------------------------------
# Lifecycle — every transition sealed onto the hash-chained audit log (the processing log).
# ---------------------------------------------------------------------------------------


def _seal(session: Session, action: str, query: str, *, when: str) -> None:
    audit_store.append(
        session,
        {
            "timestamp": when,
            "action": action,
            "domain": "compliance",
            "user_id": current_user() or "",
            "query": query,
            "intent_global": None,
            "intent_domain": None,
            "validation_status": "recorded",
            "rules_version": RULES_VERSION,
        },
    )


def _row_dict(r: DpdpRightsRequest) -> dict[str, Any]:
    return {
        "id": r.id,
        "requester": r.requester,
        "request_type": r.request_type,
        "details": r.details,
        "received_date": r.received_date,
        "due_date": r.due_date,
        "status": r.status,
        "hold_basis": r.hold_basis,
        "closed_date": r.closed_date,
    }


def create_request(
    session: Session,
    *,
    requester: str,
    request_type: str,
    received_date: str,
    details: str | None = None,
) -> dict[str, Any]:
    """Record a rights request: 90-day due date, legal-hold evaluation (erasure only), an SLA
    row in the EXISTING compliance calendar, and a sealed processing-log event. Does not commit
    — the caller's preview/commit discipline decides that (INVARIANT 9)."""
    org_id = _require_org()
    if request_type not in REQUEST_TYPES:
        raise ValueError(f"request_type must be one of {REQUEST_TYPES}, not {request_type!r}")
    date.fromisoformat(received_date)  # reject garbage before anything is written

    hold = erasure_hold(session, received_date) if request_type == "erasure" else None
    due = sla_due_date(received_date)
    row = DpdpRightsRequest(
        org_id=org_id,
        requester=requester,
        request_type=request_type,
        details=details,
        received_date=received_date,
        due_date=due,
        status="held" if hold else "open",
        hold_basis=hold,
    )
    session.add(row)
    session.flush()

    # SLA surfaced through the ONE calendar every other statutory deadline uses. The form name
    # carries the row id, not the requester — no data-principal PII in the shared calendar.
    row.calendar_deadline_id = ComplianceService().add_deadline(
        session,
        domain="dpdp",
        form_name=f"DPDP {request_type} request #{row.id} — respond",
        due_date=due,
    )
    _seal(
        session,
        "dpdp.request_created",
        f"rights request #{row.id} ({request_type}) received {received_date}, "
        f"due {due}, status {row.status}" + (f"; held: {hold}" if hold else ""),
        when=received_date,
    )
    session.flush()
    return _row_dict(row)


def list_requests(session: Session) -> list[dict[str, Any]]:
    """This org's rights requests, newest first. Org filter is load-bearing on SQLite (no RLS)."""
    org_id = _require_org()
    rows = session.scalars(
        select(DpdpRightsRequest)
        .where(DpdpRightsRequest.org_id == org_id)
        .order_by(DpdpRightsRequest.id.desc())
    ).all()
    return [_row_dict(r) for r in rows]


def close_request(session: Session, request_id: int, *, closed_date: str) -> dict[str, Any]:
    """Complete a request. For an erasure the legal hold is re-evaluated AS OF ``closed_date``
    — the check at creation time is not trusted to still be true — and a live hold raises
    :class:`LegalHoldError` with the statutory basis, writing nothing. Retained records are
    never deleted, silently or otherwise; this module never touches vault rows at all.

    Completing also files the request's row in the compliance calendar (``mark_filed`` — the
    existing machinery), so the calendar and the request can't disagree."""
    org_id = _require_org()
    row = session.get(DpdpRightsRequest, request_id)
    if row is None or row.org_id != org_id:
        raise ValueError(f"rights request {request_id} not found")
    if row.status == "completed":
        raise ValueError(f"rights request {request_id} is already completed")

    if row.request_type == "erasure":
        hold = erasure_hold(session, closed_date)
        if hold:
            # Raise WITHOUT mutating: callers roll back on error, so a state change here would
            # be silently discarded anyway. The held/basis state was set at creation.
            raise LegalHoldError(hold)

    row.status = "completed"
    row.closed_date = closed_date
    if row.calendar_deadline_id is not None:
        ComplianceService().mark_filed(
            session,
            row.calendar_deadline_id,
            filed_date=closed_date,
            acknowledgement=f"dpdp request #{row.id} completed",
        )
    _seal(
        session,
        "dpdp.request_closed",
        f"rights request #{row.id} ({row.request_type}) completed {closed_date}",
        when=closed_date,
    )
    session.flush()
    return _row_dict(row)
