"""Pydantic request/response models for the compliance API."""

from __future__ import annotations

from pydantic import BaseModel


class NewDeadline(BaseModel):
    domain: str  # roc/gst/tds/pf/esi/pt
    form_name: str
    due_date: str  # ISO
    filing_period: str | None = None


class MarkFiled(BaseModel):
    filed_date: str
    acknowledgement: str | None = None
