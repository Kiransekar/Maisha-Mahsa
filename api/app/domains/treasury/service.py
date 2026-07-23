"""Treasury service: bank-CSV import and the cash / burn / runway math.

All money is integer paise and all math is exact. Time is **injected** (`as_of`) so the
service is deterministic and testable — it never reads the clock itself.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import anchors
from app.core.domain import BaseDomainService
from app.core.money import Paise
from app.db.models.treasury import BankAccount, BankTransaction
from app.domains.treasury.manifest import MANIFEST
from app.domains.vault.service import VaultService

# Canonical field -> ordered list of header substrings seen across Indian bank statements.
_HEADER_MAP: dict[str, tuple[str, ...]] = {
    "date": ("transaction date", "tran date", "txn date", "value date", "date"),
    "description": ("narration", "transaction remarks", "particulars", "remarks", "description"),
    "reference": ("chq./ref.no.", "ref no", "cheque no", "chq/ref", "reference", "ref"),
    "debit": ("withdrawal amt", "withdrawal amount", "withdrawal", "debit", "dr"),
    "credit": ("deposit amt", "deposit amount", "deposit", "credit", "cr"),
    "balance": ("closing balance", "balance", "bal"),
}

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d/%m/%y",
    "%d-%m-%Y",
    "%d-%m-%y",
    "%d-%b-%Y",
    "%d %b %Y",
)


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return _strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _strptime(raw: str, fmt: str) -> date:
    from datetime import datetime

    return datetime.strptime(raw, fmt).date()


def _cell(row: list[str], cols: dict[str, int], field: str) -> str | None:
    """Return the trimmed cell for ``field`` if the column exists and the row is long
    enough; otherwise ``None``."""
    idx = cols.get(field)
    if idx is None or idx >= len(row):
        return None
    return row[idx].strip()


def _parse_amount(raw: str) -> Paise:
    cleaned = raw.replace(",", "").replace("₹", "").replace("Rs.", "").strip()
    if cleaned in ("", "-", "0", "0.0", "0.00"):
        return Paise(0)
    try:
        return Paise.from_rupees(Decimal(cleaned))
    except Exception:
        return Paise(0)


def _months_back(anchor: date, months: int) -> date:
    """The date ``months`` whole months before ``anchor`` (clamped to month length)."""
    total = anchor.year * 12 + (anchor.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    # clamp day to the last valid day of the target month
    import calendar

    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def upi_reconcile(bank_refs: list[dict], upi_refs: list[dict]) -> dict[str, Any]:
    """Reconcile a UPI statement against bank transactions by (reference, amount). Each entry:
    {reference, amount}. Reports matched references and what's unmatched on each side."""
    bank_keys = {(b["reference"], int(b["amount"])) for b in bank_refs}
    upi_keys = {(u["reference"], int(u["amount"])) for u in upi_refs}
    matched = [u["reference"] for u in upi_refs if (u["reference"], int(u["amount"])) in bank_keys]
    unmatched_upi = [
        u["reference"] for u in upi_refs if (u["reference"], int(u["amount"])) not in bank_keys
    ]
    unmatched_bank = [
        b["reference"] for b in bank_refs if (b["reference"], int(b["amount"])) not in upi_keys
    ]
    return {
        "matched": matched,
        "unmatched_upi": unmatched_upi,
        "unmatched_bank": unmatched_bank,
        "reconciled": not unmatched_upi and not unmatched_bank,
    }


def bank_guarantee_status(
    expiry_date: str, as_of: date, *, renewal_window_days: int = 30
) -> dict[str, Any]:
    """Track a bank guarantee's lifecycle: days to expiry, whether expired, and whether it's
    inside the renewal window."""
    days = (date.fromisoformat(expiry_date) - as_of).days
    return {
        "expiry_date": expiry_date,
        "days_to_expiry": days,
        "expired": days < 0,
        "renewal_due": 0 <= days <= renewal_window_days,
    }


def sweep_suggestion(cash: int, monthly_net_burn: int, *, buffer_months: int = 6) -> dict[str, Any]:
    """Treasury policy: keep ``buffer_months`` of net burn liquid; cash above that buffer is
    idle and can be swept into an FD ladder. Pure — exact paise."""
    buffer_required = max(0, int(monthly_net_burn)) * int(buffer_months)
    sweepable = max(0, int(cash) - buffer_required)
    return {
        "cash": int(cash),
        "buffer_months": int(buffer_months),
        "buffer_required": buffer_required,
        "sweepable": sweepable,
        "recommend_sweep": sweepable > 0,
    }


class TreasuryService(BaseDomainService):
    domain = "treasury"
    keywords = ("cash", "bank", "runway", "burn", "treasury", "balance", "fd", "deposit")
    manifest = MANIFEST

    # ---- CSV import -----------------------------------------------------------------

    def _resolve_columns(self, header: list[str]) -> dict[str, int]:
        lowered = [h.strip().lower() for h in header]
        cols: dict[str, int] = {}
        for field, candidates in _HEADER_MAP.items():
            for cand in candidates:
                idx = next((i for i, h in enumerate(lowered) if cand in h), None)
                if idx is not None:
                    cols[field] = idx
                    break
        if "date" not in cols or ("debit" not in cols and "credit" not in cols):
            raise ValueError("unrecognised bank CSV: need a date column and a debit/credit column")
        return cols

    def import_csv(
        self,
        session: Session,
        account_id: int,
        csv_text: str,
        *,
        file_name: str = "bank-statement.csv",
        raw_bytes: bytes | None = None,
        upload_date: str | None = None,
    ) -> dict[str, int]:
        """Import a bank statement CSV into ``bank_transactions`` and update the account
        balance. Returns counts + closing balance (paise).

        CITE.P0-2 (SPEC-MEMCITE-1.0 §B3.1) — vault-first, cell-citable, idempotent:
        the raw CSV bytes are ingested into the vault FIRST (content-addressed, verbatim),
        then every imported row is stamped with its citation anchor: ``source_doc_id`` (the
        file's sha256), ``source_row`` (1-based RAW line number in the original file, CSVW
        source-number semantics), ``row_hash`` (sha256 of ``canonical_json`` over the trimmed
        cells in column order), and ``occurrence`` (ordinal among identical rows in the file).
        A row whose ``(source_doc_id, row_hash, occurrence)`` already exists is skipped, so
        re-uploading the same file is a NO-OP — row counts and the account balance are
        unchanged. This fixes the previously non-idempotent re-upload.
        """
        account = session.get(BankAccount, account_id)
        if account is None:
            raise ValueError(f"bank account {account_id} not found")

        # Records with their 1-based RAW line numbers — the SAME parser the resolution
        # service (app.core.anchors, CITE.P0-3) replays at read time, so minted anchors and
        # resolved anchors can never drift apart.
        records = anchors.csv_records(csv_text)

        empty = {
            "account_id": account_id,
            "rows_imported": 0,
            "rows_skipped": 0,
            "rows_duplicate": 0,
            "closing_balance_paise": account.current_balance,
        }
        if not records:
            return empty

        cols = self._resolve_columns(records[0][1])

        # Parse pass (pure) — collect the importable rows before any write.
        parsed: list[tuple[int, list[str], date, Paise, Paise, str | None]] = []
        skipped = 0
        for line_no, row in records[1:]:
            date_raw = _cell(row, cols, "date")
            txn_date = _parse_date(date_raw) if date_raw else None
            if txn_date is None:
                skipped += 1
                continue
            debit_raw = _cell(row, cols, "debit")
            credit_raw = _cell(row, cols, "credit")
            debit = _parse_amount(debit_raw) if debit_raw else Paise(0)
            credit = _parse_amount(credit_raw) if credit_raw else Paise(0)
            if debit == 0 and credit == 0:
                skipped += 1
                continue
            parsed.append((line_no, row, txn_date, debit, credit, _cell(row, cols, "balance")))

        if not parsed:
            empty["rows_skipped"] = skipped
            return empty

        # Vault-first: the source file becomes a content-addressed document the anchors
        # resolve against. ``upload_date`` falls back to the statement's latest transaction
        # date — deterministic (no clock in the service), and retention metadata only.
        raw = raw_bytes if raw_bytes is not None else csv_text.encode("utf-8")
        doc = VaultService().ingest_bytes(
            session,
            file_name=file_name,
            content=raw,
            upload_date=upload_date or max(p[2] for p in parsed).isoformat(),
            doc_type="bank_statement",
            domain="treasury",
        )
        doc_id: str = doc["id"]
        existing_anchors = {
            (rh, occ)
            for rh, occ in session.execute(
                select(BankTransaction.row_hash, BankTransaction.occurrence).where(
                    BankTransaction.source_doc_id == doc_id
                )
            )
        }

        imported = 0
        duplicates = 0
        occurrences: dict[str, int] = {}
        running = Paise(account.current_balance)

        for line_no, row, txn_date, debit, credit, balance_raw in parsed:
            row_hash = anchors.row_hash(row)
            occ = occurrences.get(row_hash, 0) + 1
            occurrences[row_hash] = occ
            if (row_hash, occ) in existing_anchors:
                duplicates += 1  # already imported from this exact file — re-upload no-op
                continue

            running = Paise(running + credit - debit)
            balance = running
            if balance_raw:
                parsed_bal = _parse_amount(balance_raw)
                if parsed_bal != 0:
                    balance = parsed_bal
                    running = parsed_bal

            session.add(
                BankTransaction(
                    account_id=account_id,
                    txn_date=txn_date.isoformat(),
                    description=_cell(row, cols, "description"),
                    reference=_cell(row, cols, "reference"),
                    debit=int(debit),
                    credit=int(credit),
                    balance=int(balance),
                    source_doc_id=doc_id,
                    source_row=line_no,
                    row_hash=row_hash,
                    occurrence=occ,
                )
            )
            imported += 1

        account.current_balance = int(running)
        session.flush()
        return {
            "account_id": account_id,
            "rows_imported": imported,
            "rows_skipped": skipped,
            "rows_duplicate": duplicates,
            "closing_balance_paise": int(running),
        }

    # ---- metrics --------------------------------------------------------------------

    def cash_position(self, session: Session) -> dict[str, Any]:
        accounts = session.scalars(select(BankAccount)).all()
        by_account = {a.bank_name: int(a.current_balance) for a in accounts}
        total = sum(by_account.values())
        largest = max(by_account.values(), default=0)
        share = (largest / total) if total > 0 else 0.0
        return {
            "total_cash_paise": total,
            "account_count": len(accounts),
            "largest_account_share": round(share, 6),
            "by_account": by_account,
        }

    def window_totals(self, session: Session, as_of: date, months: int = 3) -> tuple[Paise, Paise]:
        """(total_debits, total_credits) in the trailing ``months`` window ending ``as_of``."""
        start = _months_back(as_of, months)
        txns = session.scalars(select(BankTransaction)).all()
        debits = 0
        credits = 0
        for t in txns:
            d = _parse_date(t.txn_date)
            if d is None or d <= start or d > as_of:
                continue
            debits += int(t.debit)
            credits += int(t.credit)
        return Paise(debits), Paise(credits)

    def burn_attribution(self, session: Session, as_of: date, months: int = 3) -> dict[str, Any]:
        """Trailing-window spend (debits) grouped by transaction category — where the burn
        actually goes. Uncategorised debits roll into 'uncategorised'."""
        start = _months_back(as_of, months)
        txns = session.scalars(select(BankTransaction)).all()
        by_category: dict[str, int] = {}
        total = 0
        for t in txns:
            d = _parse_date(t.txn_date)
            if d is None or d <= start or d > as_of or int(t.debit) <= 0:
                continue
            category = t.category or "uncategorised"
            by_category[category] = by_category.get(category, 0) + int(t.debit)
            total += int(t.debit)
        return {
            "as_of": as_of.isoformat(),
            "window_months": months,
            "total_debits_paise": total,
            "by_category": dict(sorted(by_category.items(), key=lambda kv: -kv[1])),
        }

    def treasury_policy(
        self, session: Session, as_of: date, *, buffer_months: int = 6
    ) -> dict[str, Any]:
        """Auto-sweep suggestion: idle cash beyond a ``buffer_months`` runway buffer that could
        be laddered into FDs, computed from current treasury metrics."""
        m = self.metrics(session, as_of)
        return sweep_suggestion(m["cash_paise"], m["net_burn_paise"], buffer_months=buffer_months)

    def metrics(self, session: Session, as_of: date, months: int = 3) -> dict[str, Any]:
        cash = self.cash_position(session)
        debits, credits = self.window_totals(session, as_of, months)
        monthly_burn = Paise(round(int(debits) / months))
        monthly_revenue = Paise(round(int(credits) / months))
        net_burn = Paise(max(0, int(monthly_burn) - int(monthly_revenue)))
        runway = None if net_burn == 0 else round(int(cash["total_cash_paise"]) / int(net_burn), 2)
        return {
            "as_of": as_of.isoformat(),
            "window_months": months,
            "cash_paise": cash["total_cash_paise"],
            "monthly_burn_paise": int(monthly_burn),
            "monthly_revenue_paise": int(monthly_revenue),
            "net_burn_paise": int(net_burn),
            "runway_months": runway,
            "largest_account_share": cash["largest_account_share"],
            "account_count": cash["account_count"],
        }

    # ---- Mahsa contract -------------------------------------------------------------

    def build_snapshot(self, session: Session, as_of: date | None = None) -> dict[str, Any]:
        anchor = as_of or date(1970, 1, 1)
        m = self.metrics(session, anchor)
        return {
            "as_of": m["as_of"],
            "cash": m["cash_paise"],
            "monthly_burn": m["monthly_burn_paise"],
            "monthly_revenue": m["monthly_revenue_paise"],
            "bank_account_count": m["account_count"],
            "largest_account_share": m["largest_account_share"],
        }
