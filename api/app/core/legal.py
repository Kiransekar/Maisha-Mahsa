"""WS10.4 — legal kit: versioned ToS/Privacy/DPA + acceptance log + the disclaimer string.

DRAFTS FOR COUNSEL REVIEW — see ``docs/legal/``. This module enforces mechanics only (record
which org's user accepted which version when; require re-acceptance after a version bump). It
makes no legal judgment and asserts no compliance with any law — §0.6 (never invent a statutory
value, cite a primary instrument or mark BLOCKED) applies to legal claims exactly as it does to
tax figures, so nothing here should be read as a compliance assertion.

Two §0.8 properties are load-bearing and are enforced here rather than left to callers:

* **org_id is never a parameter.** Every read and write scopes to
  :func:`app.core.principal.current_org` — the org the authentication middleware bound from a
  VERIFIED JWT claim. A caller cannot pass an org from a request body because there is nowhere
  to pass one, and with no bound org every function raises rather than falling back to "all
  orgs". Postgres RLS on ``legal_acceptance`` is the second line of defence; this filter is the
  first, and it is the only one on SQLite (dev/test).
* **queries are parameterised** (SQLAlchemy Core), and no PII is logged — nothing here logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.principal import current_org
from app.db.models.legal import LegalAcceptance

# Byte-exact per §WS10.4 — render this verbatim everywhere an output is shown. Do not reword,
# translate, or truncate; a paraphrase is not the disclaimer the ticket specifies.
DISCLAIMER_TEXT = (
    "software tool, not the practice of chartered accountancy; "
    "outputs require professional verification"
)


class DocType(StrEnum):
    TOS = "tos"
    PRIVACY = "privacy"
    DPA = "dpa"
    #: WS10.1 — the DPDP consent/notice document (docs/legal/DPDP_NOTICE_DRAFT.md). Same
    #: versioned-acceptance mechanics as the others; the Postgres CHECK constraint admits it
    #: via migration 0010_dpdp_rights.
    DPDP_NOTICE = "dpdp_notice"


class OrgUnboundError(RuntimeError):
    """No verified org is bound to this request/task — fail closed rather than read or write
    an acceptance log across tenants (§0.8)."""


@dataclass(frozen=True)
class PublishedVersion:
    """One published version of one document type.

    ``effective_at`` is AUTHORITATIVE, not decorative: :func:`current_version` resolves the
    in-force version by it, so a row dated in the future is not yet in force and does not
    trigger re-acceptance. (The previous implementation declared and stored ``effective_at``
    and then resolved "in force" by row insertion order, so the field looked authoritative and
    was ignored — the trap this ticket's item 3 names.)
    """

    doc_type: DocType
    version: str
    effective_at: datetime
    doc_path: str  # e.g. docs/legal/TOS_DRAFT.md


#: The published legal documents. EMPTY — every document in ``docs/legal/`` is still headed
#: "DRAFT FOR COUNSEL REVIEW" and carries ``TODO(counsel)`` markers, so nothing is published
#: and nothing can be accepted yet. Listing a draft here would be exactly the invented legal
#: assertion §0.6 forbids.
#:
#: ponytail: a code constant, not a table. ``doc_path`` points at a repo file, so publishing a
#: version already requires a deploy — a DB registry could never be more current than the code,
#: and it would have added a second non-tenant table for the RLS gate to argue about. Upgrade
#: path if legal ever needs to publish without a deploy: move the text into object storage and
#: this tuple into a table, and give it the same org-scoped treatment as the acceptance log.
PUBLISHED: tuple[PublishedVersion, ...] = ()


def _require_org() -> str:
    org = current_org()
    if not org:
        raise OrgUnboundError(
            "no verified org bound to this request; refusing to touch the acceptance log"
        )
    return org


def current_version(
    doc_type: DocType,
    now: datetime,
    published: tuple[PublishedVersion, ...] = PUBLISHED,
) -> str | None:
    """The version of ``doc_type`` in force at ``now``, or ``None`` if none is yet.

    In force = the latest ``effective_at`` that is not in the future. Later registry entries
    win an exact ``effective_at`` tie (registry order is publication order).
    """
    best: PublishedVersion | None = None
    for entry in published:
        if entry.doc_type != doc_type or entry.effective_at > now:
            continue
        if best is None or entry.effective_at >= best.effective_at:
            best = entry
    return best.version if best else None


def record_acceptance(
    session: Session,
    user_id: str,
    doc_type: DocType,
    version: str,
    now: datetime,
    published: tuple[PublishedVersion, ...] = PUBLISHED,
) -> LegalAcceptance:
    """Append one acceptance event for the CURRENT org's ``user_id``. Never updates a prior
    row — the log itself is the evidence, so history is only ever added to.

    ``version`` must be one this registry actually published for ``doc_type``: an acceptance
    naming a version that never existed is unfalsifiable evidence, which is worse than none.
    """
    org_id = _require_org()
    if not any(e.doc_type == doc_type and e.version == version for e in published):
        raise ValueError(f"{doc_type.value} version {version!r} was never published")
    row = LegalAcceptance(
        org_id=org_id,
        user_id=user_id,
        doc_type=doc_type.value,
        version=version,
        accepted_at=now.isoformat(),
    )
    session.add(row)
    session.flush()
    return row


def latest_acceptance(session: Session, user_id: str, doc_type: DocType) -> LegalAcceptance | None:
    """The most recent acceptance by ``user_id`` **of this document type**, in the current org.

    All three filters are load-bearing. Dropping ``doc_type`` would report a user who accepted
    the Privacy Policy as having accepted the ToS; dropping ``org_id`` would read another
    tenant's log on SQLite, where there is no RLS to catch it.
    """
    org_id = _require_org()
    return session.scalars(
        select(LegalAcceptance)
        .where(
            LegalAcceptance.org_id == org_id,
            LegalAcceptance.user_id == user_id,
            LegalAcceptance.doc_type == doc_type.value,
        )
        .order_by(LegalAcceptance.accepted_at.desc(), LegalAcceptance.id.desc())
        .limit(1)
    ).first()


class ReacceptanceRequiredError(ValueError):
    """WS10.1 — the caller must (re)accept the in-force version of a document before the
    gated action proceeds. Subclasses ValueError so the web action layer's existing 422
    handling surfaces the message and writes nothing."""


def require_current_acceptance(
    session: Session,
    user_id: str | None,
    doc_type: DocType,
    now: datetime,
    published: tuple[PublishedVersion, ...] = PUBLISHED,
) -> None:
    """WS10.1 consent gate for onboarding / employee-data ingestion: raise unless ``user_id``
    has accepted the version of ``doc_type`` in force at ``now``.

    Nothing published → no-op (nothing exists to accept — the honest state while every
    document is still a counsel-gated draft, same stance as :func:`needs_reacceptance`).
    Something published + no verified user → fail CLOSED: an unattributable caller cannot
    have accepted anything.
    """
    current = current_version(doc_type, now, published)
    if current is None:
        return
    if not user_id or needs_reacceptance(session, user_id, doc_type, now, published):
        raise ReacceptanceRequiredError(
            f"the current {doc_type.value} (version {current}) must be accepted before this "
            "action — see Settings → Privacy"
        )


def require_terms_acceptance(
    session: Session,
    user_id: str | None,
    now: datetime,
    published: tuple[PublishedVersion, ...] = PUBLISHED,
) -> None:
    """WS10.4 — the ToS + Privacy gate for the sign-in/first-mutation surface: raise unless the
    verified caller has accepted the IN-FORCE version of both documents.

    Same mechanics and same dormancy as the WS10.1 DPDP-notice gate: while nothing is published
    (every document in ``docs/legal/`` is still a counsel-gated draft) this is a no-op, and the
    moment counsel publishes a version — or bumps one — the gate goes live with no code change.
    """
    for doc in (DocType.TOS, DocType.PRIVACY):
        require_current_acceptance(session, user_id, doc, now, published)


def needs_reacceptance(
    session: Session,
    user_id: str,
    doc_type: DocType,
    now: datetime,
    published: tuple[PublishedVersion, ...] = PUBLISHED,
) -> bool:
    """True when the user has never accepted ``doc_type``, or last accepted a version that is
    no longer the one in force at ``now`` — i.e. a version bump forces re-acceptance (§WS10.4).
    """
    current = current_version(doc_type, now, published)
    if current is None:
        return False  # nothing in force yet — nothing to (re)accept
    last = latest_acceptance(session, user_id, doc_type)
    return last is None or last.version != current
