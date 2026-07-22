"""Shared tables (PRD §3.1). Money columns are INTEGER **paise** (see CLAUDE.md §2 /
BUILD_PROGRESS deviation note) rather than the PRD's illustrative REAL, for exactness."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Company(Base):
    __tablename__ = "company"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    cin: Mapped[str | None] = mapped_column(String, unique=True)
    pan: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    gstin: Mapped[str | None] = mapped_column(String, unique=True)
    incorporation_date: Mapped[str | None] = mapped_column(String)
    financial_year_end: Mapped[str] = mapped_column(String, default="03-31")
    msme_registration: Mapped[str | None] = mapped_column(String)
    dpiit_recognition: Mapped[str | None] = mapped_column(String)
    sector: Mapped[str | None] = mapped_column(String)
    address: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="founder")
    expertise: Mapped[str] = mapped_column(String, default="founder")
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class AuditLog(Base):
    """Append-only, hash-chained (PRD §11.2). Application code must never UPDATE/DELETE."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    query: Mapped[str | None] = mapped_column(Text)
    intent_global: Mapped[str | None] = mapped_column(Text)  # JSON array
    intent_domain: Mapped[str | None] = mapped_column(Text)  # JSON array
    validation_status: Mapped[str | None] = mapped_column(String)
    rules_version: Mapped[str] = mapped_column(String, nullable=False)
    prev_hash: Mapped[str | None] = mapped_column(String)
    this_hash: Mapped[str | None] = mapped_column(String)


class LlmTrace(Base):
    """Observability for the drafting layer (separate from the tamper-evident audit_log).
    Stores hashes, not raw prompts, so a run is reproducible without persisting sensitive
    text: ``input_sha256`` keys (domain+query+snapshot), ``claim_sha256`` keys the draft."""

    __tablename__ = "llm_trace"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    audit_hash: Mapped[str | None] = mapped_column(String)  # links to audit_log.this_hash
    model_label: Mapped[str] = mapped_column(String, nullable=False)
    input_sha256: Mapped[str] = mapped_column(String, nullable=False)
    claim_sha256: Mapped[str | None] = mapped_column(String)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    verified: Mapped[int] = mapped_column(Integer, default=0)  # 1 = every number fact-backed
    requires_approval: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)  # wall-clock of the draft step


class MetricSnapshot(Base):
    """A point-in-time capture of one domain metric, for trend charts (observability only —
    never a money-math input, so a float is fine here). One row per scalar fact per capture."""

    __tablename__ = "metric_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    captured_at: Mapped[str] = mapped_column(String, nullable=False)  # ISO date/datetime
    domain: Mapped[str] = mapped_column(String, nullable=False)
    metric: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)


class ParallelRun(Base):
    """A Layer-6 parallel run: Maisha runs alongside the founder's existing process for a
    period; daily we reconcile their figures against Maisha's before cut-over."""

    __tablename__ = "parallel_run"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    started_on: Mapped[str] = mapped_column(String, nullable=False)  # ISO date
    ends_on: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="active")  # active | closed


class ParallelObservation(Base):
    """A figure the founder's existing system reports, to be reconciled against Maisha's
    metric of the same (domain, metric) for that date. Same unit as the Maisha metric
    (paise for money)."""

    __tablename__ = "parallel_observation"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_on: Mapped[str] = mapped_column(String, nullable=False)  # ISO date
    domain: Mapped[str] = mapped_column(String, nullable=False)
    metric: Mapped[str] = mapped_column(String, nullable=False)
    external_value: Mapped[float] = mapped_column(Float, nullable=False)


class Decision(Base):
    """A human approve/reject on a flagged domain state (F4). Keyed by ``state_hash`` (a hash
    of the snapshot), so a decision resolves the queue only until the underlying books change —
    then the item resurfaces for re-approval. Each decision is also sealed into ``audit_log``."""

    __tablename__ = "decision"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)  # "approved" | "rejected"
    state_hash: Mapped[str] = mapped_column(String, nullable=False)
    audit_hash: Mapped[str | None] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    # WS7-E2E fix:bulk-rows — WHICH inbox row this decision covered (e.g. "approval:gst").
    # NULL for pre-fix rows and for whole-domain decisions from the approvals page.
    item_id: Mapped[str | None] = mapped_column(String)


class Org(Base):
    """Tenancy root — dev/SQLite mirror of ``tenant_core.orgs`` (infra 001_tenancy.sql).
    Scheduled jobs iterate these rows (WS4.5); ``plan`` is the entitlement tier (WS6)."""

    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    plan: Mapped[str] = mapped_column(String, nullable=False, default="basics")
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class AppUser(Base):
    """Global identity — dev/SQLite mirror of ``app_users`` (infra 001_tenancy.sql). NOT a
    parallel auth system: Better Auth owns credentials/sessions (WS4.3); this row only anchors
    memberships to an email so an invite can precede the invitee's first login."""

    __tablename__ = "app_users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class Membership(Base):
    """User↔org binding with a role — dev/SQLite mirror of ``memberships`` (infra
    001_tenancy.sql + the ``status`` column added by migration 0007). ``status`` is
    'pending' from a WS8.3 invite until the invitee accepts, then 'active'."""

    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # owner|admin|…|ca|investor
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")  # pending|active
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class JobRun(Base):
    """WS4.5 — idempotency ledger for scheduled jobs: one row per (org, job, period).

    A re-run for a period the job already COMPLETED ('done') is a no-op; an 'error' row does
    NOT block a retry. ``org_id`` is 'default' on the legacy single-tenant dev path."""

    __tablename__ = "job_run"
    __table_args__ = (UniqueConstraint("org_id", "job", "period", name="uq_job_run_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String, nullable=False)
    job: Mapped[str] = mapped_column(String, nullable=False)
    period: Mapped[str] = mapped_column(String, nullable=False)  # ISO date the run covered
    status: Mapped[str] = mapped_column(String, nullable=False)  # done | error
    ran_at: Mapped[str] = mapped_column(String, nullable=False)  # ISO timestamp


class CaThread(Base):
    """WS8.2 — a CA query pinned to a ledger entry / figure reference. States:
    open -> responded -> resolved. Every transition also seals a ``ca_thread.*`` event onto the
    hash-chained ``audit_log`` (see ``app.core.ca_threads``); these rows are the queryable
    mirror, never the source of truth for tamper-evidence."""

    __tablename__ = "ca_thread"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)  # ISO timestamp
    domain: Mapped[str] = mapped_column(String, nullable=False)
    entry_ref: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "journal:42"
    question: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String, default="open")  # open | responded | resolved
    raised_by: Mapped[str] = mapped_column(String, nullable=False)


class CaThreadEvent(Base):
    """One append-only event on a :class:`CaThread` (raise / respond / resolve).
    ``audit_hash`` links to the sealed ``audit_log.this_hash`` for this event; the raw ``note``
    text lives ONLY here — the audit descriptor carries its sha256 (no PII in the chain)."""

    __tablename__ = "ca_thread_event"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    thread_id: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[str] = mapped_column(String, nullable=False)
    event: Mapped[str] = mapped_column(String, nullable=False)  # raise | respond | resolve
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    doc_id: Mapped[str | None] = mapped_column(String)  # vault documents.id (respond-with-doc)
    audit_hash: Mapped[str | None] = mapped_column(String)


class ComplianceCalendar(Base):
    __tablename__ = "compliance_calendar"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    form_name: Mapped[str] = mapped_column(String, nullable=False)
    due_date: Mapped[str] = mapped_column(String, nullable=False)
    filing_period: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    filed_date: Mapped[str | None] = mapped_column(String)
    acknowledgement: Mapped[str | None] = mapped_column(String)
    penalty_amount: Mapped[int] = mapped_column(Integer, default=0)  # paise
    reminder_sent: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())


class RulesRegistry(Base):
    __tablename__ = "rules_registry"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    rule_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    statute: Mapped[str | None] = mapped_column(String)
    section: Mapped[str | None] = mapped_column(String)
    condition_logic: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String, default="warning")
    active: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(server_default=func.current_timestamp())
