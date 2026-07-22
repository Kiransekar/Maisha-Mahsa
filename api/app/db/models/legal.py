"""WS10.4 — legal kit table: an append-only acceptance log.

DRAFTS FOR COUNSEL REVIEW — the documents this log points at (``docs/legal/``) are NOT final
legal text (see the header of each). This module stores only the *mechanical* fact of which
org's user accepted which version when; it makes no legal determination and asserts compliance
with no law (§0.6 applies to legal claims exactly as to statutory figures).

TENANT-SCOPED (§0.8). An acceptance is a fact about a *customer org* — the org's user bound the
org to a ToS/DPA version — so the row carries ``org_id`` and is protected by row-level security
keyed on the session's org in ``infra/db/multitenant/004_legal.sql`` / Alembic
``0004_legal_acceptance``. The ``org_id`` written here comes from
:func:`app.core.principal.current_org`, i.e. the verified JWT claim, never a request body.

There is deliberately NO ``legal_document`` table. The set of published versions is not tenant
data and is not runtime data: each row would have held a ``doc_path`` pointing at a file in
``docs/legal/`` that only a deploy can change, so a DB registry could never be more current than
the code. It lives in code as :data:`app.core.legal.PUBLISHED` instead — see that docstring.
"""

from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LegalAcceptance(Base):
    """Append-only: one row per acceptance event. Never updated or deleted — the log itself is
    the evidence that a given org's user accepted a given version at a given time. The Postgres
    grant in the migration withholds UPDATE/DELETE from the app role to enforce that."""

    __tablename__ = "legal_acceptance"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False)  # tenant boundary (RLS key)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    doc_type: Mapped[str] = mapped_column(String, nullable=False)  # tos | privacy | dpa
    version: Mapped[str] = mapped_column(String, nullable=False)
    accepted_at: Mapped[str] = mapped_column(String, nullable=False)  # ISO datetime

    __table_args__ = (Index("legal_acceptance_lookup", "org_id", "user_id", "doc_type"),)
