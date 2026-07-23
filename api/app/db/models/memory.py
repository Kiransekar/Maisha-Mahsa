"""SPEC-MEMCITE-1.0 §A2 (MEM.P0-1) — per-company memory layer, dev/SQLite mirrors of
``tenant_core`` (``infra/db/multitenant/009_org_memory.sql`` / Alembic ``0011_org_memory``,
which ships the RLS policies in the same migration, §0.8).

TENANT-SCOPED. ``org_id`` is the tenant boundary (RLS key) and comes ONLY from the verified
:class:`app.core.principal.Principal` — never a request body and never a first-row fallback
(the api-nest ``resolveCompanyId()`` defect this port fixes, spec §A3).

§0.4 guardrail lives one layer up: memory content is CONTEXT for the agent, never a figure
source — it is never merged into the deterministic facts map (see ``app.core.memory``).
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrgMemory(Base):
    """The CFO posture block: explicit-write-only durable preferences, hard-capped at 2200
    chars with reject-on-overflow (never silent truncation). One row per (org, kind); the cap
    is the forgetting-pressure mechanism (survey §5.2.3) and is also DB-enforced."""

    __tablename__ = "org_memory"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False)  # tenant boundary (RLS key)
    kind: Mapped[str] = mapped_column(String, nullable=False, default="cfo_posture")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)  # ISO datetime
    updated_by: Mapped[str] = mapped_column(String, nullable=False)  # Principal.user_id

    __table_args__ = (
        UniqueConstraint("org_id", "kind", name="uq_org_memory_kind"),
        CheckConstraint("length(content) <= 2200", name="org_memory_content_cap"),
    )


class OrgMemoryHistory(Base):
    """Soft/temporal updates (survey §5.2.2): a superseded posture version is archived here,
    never overwritten or deleted by a write. ``audit_seq`` is the row id of the sealed
    ``memory.update`` audit event that superseded it — the auditable-updates link (§7.7)."""

    __tablename__ = "org_memory_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False)  # tenant boundary (RLS key)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    superseded_at: Mapped[str] = mapped_column(String, nullable=False)  # ISO datetime
    superseded_by: Mapped[str] = mapped_column(String, nullable=False)  # Principal.user_id
    audit_seq: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("org_memory_history_org", "org_id", "kind"),)


class PlaybookFeedback(Base):
    """Experiential memory: this org's adopt/dismiss verdict per tax playbook. One row per
    (org, playbook); latest verdict wins via upsert. A dismissed move is demoted and its
    claimed saving zeroed out of the quantified total (the verified ₹800→₹0 behaviour)."""

    __tablename__ = "playbook_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False)  # tenant boundary (RLS key)
    playbook_id: Mapped[str] = mapped_column(String, nullable=False)
    verdict: Mapped[str] = mapped_column(String, nullable=False)  # adopted | dismissed
    created_at: Mapped[str] = mapped_column(String, nullable=False)  # ISO datetime
    created_by: Mapped[str] = mapped_column(String, nullable=False)  # Principal.user_id

    __table_args__ = (UniqueConstraint("org_id", "playbook_id", name="uq_playbook_feedback"),)
