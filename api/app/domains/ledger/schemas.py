"""Pydantic request/response models for the ledger API. Money in **paise**."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NewAccount(BaseModel):
    code: str
    name: str
    account_type: str  # asset/liability/equity/income/expense
    sub_type: str | None = None
    opening_balance: int = 0


class JournalLineInput(BaseModel):
    account_id: int
    debit: int = 0
    credit: int = 0
    description: str | None = None


class NewJournalEntry(BaseModel):
    entry_date: str
    description: str
    reference: str | None = None
    source: str = "manual"
    lines: list[JournalLineInput] = Field(default_factory=list)


class JournalEntryResult(BaseModel):
    journal_entry_id: int
    total_debit: int
    total_credit: int
