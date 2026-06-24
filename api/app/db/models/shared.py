"""Shared tables (PRD §3.1). Money columns are INTEGER **paise** (see CLAUDE.md §2 /
BUILD_PROGRESS deviation note) rather than the PRD's illustrative REAL, for exactness."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String, Text, func
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
