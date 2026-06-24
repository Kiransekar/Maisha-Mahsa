"""F3 — the web action layer. A declarative registry of domain actions the UI renders as a
drawer form and POSTs to. Handlers call the existing domain services directly (the JSON
``/api/*`` routes stay untouched) and return a short status message for the toast.

Money fields are entered in rupees and converted to exact paise here at the edge. Adding an
action is config: declare its fields + a handler; the drawer, routing and toast are generic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.money import Paise
from app.domains.compliance.service import ComplianceService
from app.domains.equity.service import EquityService
from app.domains.expense.service import ExpenseService
from app.domains.ledger.service import LedgerService
from app.domains.vault.service import VaultService


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    type: str = "text"  # text | number | date | select
    required: bool = True
    placeholder: str = ""
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Action:
    domain: str
    key: str
    label: str
    fields: tuple[Field, ...]
    handler: Callable[[Session, dict[str, str]], str]


# ── handlers ──────────────────────────────────────────────────────────────────────

def _create_account(session: Session, d: dict[str, str]) -> str:
    LedgerService().create_account(
        session, code=d["code"], name=d["name"], account_type=d["account_type"]
    )
    return f"Account {d['code']} — {d['name']} created."


def _add_deadline(session: Session, d: dict[str, str]) -> str:
    ComplianceService().add_deadline(
        session,
        domain=d["domain"],
        form_name=d["form_name"],
        due_date=d["due_date"],
        filing_period=d.get("filing_period") or None,
    )
    return f"Deadline '{d['form_name']}' added (due {d['due_date']})."


def _add_shareholder(session: Session, d: dict[str, str]) -> str:
    shares = int(d["shares_held"])
    EquityService().add_shareholder(
        session, name=d["name"], category=d["category"], shares_held=shares
    )
    return f"Shareholder {d['name']} ({shares:,} shares) added."


def _submit_claim(session: Session, d: dict[str, str]) -> str:
    ExpenseService().submit_claim(
        session,
        claim_date=d["claim_date"],
        expense_date=d["expense_date"],
        category=d["category"],
        amount=Paise.from_rupees(d["amount"]),
    )
    return f"Expense claim ₹{d['amount']} ({d['category']}) submitted."


def _ingest_document(session: Session, d: dict[str, str]) -> str:
    VaultService().ingest(
        session, file_name=d["file_name"], content=d["content"], upload_date=d["upload_date"]
    )
    return f"Document '{d['file_name']}' ingested."


# ── registry ──────────────────────────────────────────────────────────────────────

_ACCOUNT_TYPES = ("asset", "liability", "equity", "income", "expense")
_SHAREHOLDER_CATS = ("founder", "investor", "esop", "advisor")

ACTIONS: dict[str, list[Action]] = {
    "ledger": [
        Action("ledger", "create-account", "Create account", (
            Field("code", "Account code", placeholder="1000"),
            Field("name", "Name", placeholder="Cash"),
            Field("account_type", "Type", type="select", options=_ACCOUNT_TYPES),
        ), _create_account),
    ],
    "compliance": [
        Action("compliance", "add-deadline", "Add deadline", (
            Field("domain", "Domain", placeholder="gst"),
            Field("form_name", "Form name", placeholder="GSTR-3B (Jun)"),
            Field("due_date", "Due date", type="date"),
            Field("filing_period", "Filing period", required=False, placeholder="2026-06"),
        ), _add_deadline),
    ],
    "equity": [
        Action("equity", "add-shareholder", "Add shareholder", (
            Field("name", "Name", placeholder="Founder"),
            Field("category", "Category", type="select", options=_SHAREHOLDER_CATS),
            Field("shares_held", "Shares held", type="number", placeholder="700000"),
        ), _add_shareholder),
    ],
    "expense": [
        Action("expense", "submit-claim", "Submit claim", (
            Field("claim_date", "Claim date", type="date"),
            Field("expense_date", "Expense date", type="date"),
            Field("category", "Category", placeholder="travel"),
            Field("amount", "Amount (₹)", type="number", placeholder="5000"),
        ), _submit_claim),
    ],
    "vault": [
        Action("vault", "ingest", "Ingest document", (
            Field("file_name", "File name", placeholder="contract.pdf"),
            Field("content", "Content / OCR text", placeholder="master services agreement…"),
            Field("upload_date", "Upload date", type="date"),
        ), _ingest_document),
    ],
}


def actions_for(domain: str) -> list[Action]:
    return ACTIONS.get(domain, [])


def find_action(domain: str, key: str) -> Action | None:
    return next((a for a in ACTIONS.get(domain, []) if a.key == key), None)
