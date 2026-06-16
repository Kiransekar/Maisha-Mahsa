"""Expense domain tables (PRD §3.11). Money columns are INTEGER **paise**."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExpenseClaim(Base):
    __tablename__ = "expense_claims"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    claim_date: Mapped[str] = mapped_column(String, nullable=False)
    expense_date: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # paise
    gst_amount: Mapped[int] = mapped_column(Integer, default=0)
    vendor_name: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)
    receipt_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    over_policy: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="submitted")
    approved_by: Mapped[str | None] = mapped_column(String)
    approved_date: Mapped[str | None] = mapped_column(String)
    reimbursement_date: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(server_default=func.current_timestamp())
