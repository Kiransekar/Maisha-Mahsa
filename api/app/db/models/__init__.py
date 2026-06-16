"""Importing this package registers every ORM model on ``Base.metadata`` so that
``create_all`` builds the schema. Add a domain's models import here as it is built."""

from app.db.models import (  # noqa: F401
    equity,
    expense,
    forecast,
    gst,
    ledger,
    payables,
    payroll,
    revenue,
    shared,
    tax,
    treasury,
    vault,
)

__all__ = [
    "equity",
    "expense",
    "forecast",
    "gst",
    "ledger",
    "payables",
    "payroll",
    "revenue",
    "shared",
    "tax",
    "treasury",
    "vault",
]
