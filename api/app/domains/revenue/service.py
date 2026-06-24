"""Revenue service: invoicing, AR aging, dunning, credit notes, the GSTR-1 bridge, and the
revenue health snapshot for Mahsa. Exact paise; deterministic (``as_of`` injected)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.domain import BaseDomainService
from app.db.models.revenue import Customer, Invoice, InvoiceItem
from app.db.models.shared import Company
from app.domains.revenue import revenue_calc
from app.domains.revenue.manifest import MANIFEST


class RevenueService(BaseDomainService):
    domain = "revenue"
    keywords = (
        "invoice",
        "customer",
        "receivable",
        "ar",
        "dunning",
        "credit note",
        "revenue",
        "irn",
        "e-invoice",
        "billing",
    )
    manifest = MANIFEST

    # ---- invoicing ------------------------------------------------------------------

    def _supplier_state(self, session: Session) -> str | None:
        company = session.scalars(select(Company)).first()
        return company.state if company else None

    def create_invoice(
        self,
        session: Session,
        *,
        invoice_number: str,
        customer_id: int,
        invoice_date: str,
        lines: list[dict],
        gst_rate: float = 18.0,
        irn: str | None = None,
        status: str = "issued",
    ) -> dict[str, Any]:
        customer = session.get(Customer, customer_id)
        if customer is None:
            raise ValueError(f"customer {customer_id} not found")

        supplier_state = self._supplier_state(session)
        # Inter-state when both states are known and differ; default intra-state otherwise.
        inter_state = bool(supplier_state and customer.state and supplier_state != customer.state)
        comp = revenue_calc.compute_invoice(
            lines,
            gst_rate=gst_rate,
            inter_state=inter_state,
            tds_rate=customer.tds_rate if customer.tds_applicable else 0,
        )

        due = (
            date.fromisoformat(invoice_date) + timedelta(days=customer.payment_terms)
        ).isoformat()
        invoice = Invoice(
            invoice_number=invoice_number,
            customer_id=customer_id,
            invoice_date=invoice_date,
            due_date=due,
            subtotal=comp["subtotal"],
            gst_rate=gst_rate,
            igst_amount=comp["igst_amount"],
            cgst_amount=comp["cgst_amount"],
            sgst_amount=comp["sgst_amount"],
            total_amount=comp["total_amount"],
            tds_amount=comp["tds_amount"],
            net_receivable=comp["net_receivable"],
            irn=irn,
            status=status,
        )
        session.add(invoice)
        session.flush()
        for ln in lines:
            session.add(
                InvoiceItem(
                    invoice_id=invoice.id,
                    description=ln.get("description", ""),
                    hsn_code=ln.get("hsn_code"),
                    quantity=int(ln["quantity"]),
                    rate=int(ln["rate"]),
                    amount=int(ln["quantity"]) * int(ln["rate"]),
                )
            )
        session.flush()
        return {"invoice_id": invoice.id, "invoice_number": invoice_number, "due_date": due, **comp}

    def record_payment(
        self, session: Session, invoice_id: int, amount: int, paid_date: str
    ) -> None:
        invoice = session.get(Invoice, invoice_id)
        if invoice is None:
            raise ValueError(f"invoice {invoice_id} not found")
        invoice.paid_amount = int(invoice.paid_amount) + int(amount)
        if invoice.paid_amount >= invoice.net_receivable:
            invoice.status = "paid"
            invoice.paid_date = paid_date
        session.flush()

    # ---- AR aging / dunning ---------------------------------------------------------

    def _open_receivables(self, session: Session) -> list[Invoice]:
        invoices = session.scalars(select(Invoice).where(Invoice.status != "draft")).all()
        return [i for i in invoices if int(i.net_receivable) - int(i.paid_amount) > 0]

    def ar_aging(self, session: Session, as_of: date) -> dict[str, Any]:
        receivables = [
            {
                "due_date": i.due_date,
                "outstanding_paise": int(i.net_receivable) - int(i.paid_amount),
            }
            for i in self._open_receivables(session)
        ]
        return revenue_calc.ar_aging(receivables, as_of)

    def due_dunning(self, session: Session, as_of: date) -> list[dict[str, str]]:
        out = []
        for i in self._open_receivables(session):
            for label in revenue_calc.dunning_due(i.due_date, as_of):
                out.append({"invoice_number": i.invoice_number, "reminder": label})
        return out

    def pending_dunning(self, session: Session, as_of: date) -> list[dict[str, Any]]:
        """Open invoices whose dunning schedule fires on ``as_of`` — with the customer + amount
        needed to send a reminder. ``stage`` is the schedule label (T-7 … T+7)."""
        out: list[dict[str, Any]] = []
        for inv in self._open_receivables(session):
            labels = revenue_calc.dunning_due(inv.due_date, as_of)
            if not labels:
                continue
            customer = session.get(Customer, inv.customer_id)
            out.append(
                {
                    "invoice_number": inv.invoice_number,
                    "customer_name": customer.name if customer else "",
                    "customer_email": customer.email if customer else None,
                    "outstanding": int(inv.net_receivable) - int(inv.paid_amount),
                    "due_date": inv.due_date,
                    "stage": labels[0],
                }
            )
        return out

    async def dunning_run(
        self, session: Session, as_of: date, channel: Any, *, company_name: str = "Maisha-Mahsa"
    ) -> dict[str, Any]:
        """Dispatch a dunning reminder for each invoice due on ``as_of``. Invoices without a
        customer email are skipped (reported, not sent). ``channel`` is an ``EmailChannel``."""
        from app.core.email.compose import compose_dunning

        pending = self.pending_dunning(session, as_of)
        sent = 0
        skipped: list[str] = []
        for item in pending:
            if not item["customer_email"]:
                skipped.append(item["invoice_number"])
                continue
            await channel.send_dunning(
                to=item["customer_email"],
                ctx=compose_dunning(item, as_of.isoformat()),
                company_name=company_name,
            )
            sent += 1
        return {
            "as_of": as_of.isoformat(),
            "pending": len(pending),
            "sent": sent,
            "skipped_no_email": skipped,
        }

    def customer_concentration(self, session: Session) -> dict[str, Any]:
        by_customer: dict[int, int] = {}
        for i in self._open_receivables(session):
            outstanding = int(i.net_receivable) - int(i.paid_amount)
            by_customer[i.customer_id] = by_customer.get(i.customer_id, 0) + outstanding
        total = sum(by_customer.values())
        largest = max(by_customer.values(), default=0)
        ratio = (largest / total) if total > 0 else 0.0
        return {"total_outstanding": total, "largest": largest, "ratio": round(ratio, 6)}

    # ---- GST bridge -----------------------------------------------------------------

    def gstr1_lines(self, session: Session, filing_period: str) -> list[dict[str, Any]]:
        """Outward-supply lines for a period ("YYYY-MM") in the shape GST's GSTR-1 builder
        expects. One line per invoice; HSN taken from the first item."""
        lines = []
        for inv in session.scalars(select(Invoice).where(Invoice.status != "draft")).all():
            if not inv.invoice_date.startswith(filing_period):
                continue
            customer = session.get(Customer, inv.customer_id)
            first_item = session.scalars(
                select(InvoiceItem).where(InvoiceItem.invoice_id == inv.id)
            ).first()
            lines.append(
                {
                    "invoice_no": inv.invoice_number,
                    "taxable": int(inv.subtotal),
                    "igst": int(inv.igst_amount),
                    "cgst": int(inv.cgst_amount),
                    "sgst": int(inv.sgst_amount),
                    "hsn": first_item.hsn_code if first_item else None,
                    "gstin": customer.gstin if customer else None,
                }
            )
        return lines

    # ---- Mahsa contract -------------------------------------------------------------

    def build_snapshot(self, session: Session, as_of: date | None = None) -> dict[str, Any]:
        anchor = as_of or date(1970, 1, 1)
        aging = self.ar_aging(session, anchor)
        total_ar = aging["total_outstanding"]
        overdue_90 = aging["buckets"]["90+"]
        credit_risk = 1.0 - (overdue_90 / total_ar) if total_ar > 0 else 1.0

        concentration = self.customer_concentration(session)
        conc_ratio = concentration["ratio"]

        # Trailing-12-month turnover and IRN coverage across issued invoices.
        cutoff = (anchor - timedelta(days=365)).isoformat()
        issued = [
            i
            for i in session.scalars(select(Invoice).where(Invoice.status != "draft")).all()
            if cutoff < i.invoice_date <= anchor.isoformat()
        ]
        annual_turnover_paise = sum(int(i.total_amount) for i in issued)
        missing_irn = sum(1 for i in issued if not i.irn)
        irn_coverage = (len(issued) - missing_irn) / len(issued) if issued else 1.0

        return {
            "as_of": anchor.isoformat(),
            "monthly_revenue": sum(int(i.total_amount) for i in issued) // 12,
            "metrics": {
                "ar_turnover": 1.0,
                "dunning_effectiveness": 1.0,
                "credit_risk": max(0.0, credit_risk),
                "revenue_quality": 1.0,
                "deferred_revenue": 1.0,
                "export_ratio": 1.0,
                "irn_coverage": irn_coverage,
                "customer_concentration": max(0.0, 1.0 - conc_ratio),
                # signals for REVENUE-001 / REVENUE-002
                "annual_turnover_rupees": annual_turnover_paise // 100,
                "einvoice_missing": missing_irn,
                "customer_concentration_ratio": conc_ratio,
            },
        }
