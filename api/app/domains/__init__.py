"""The 12 domain modules. ``build_registry`` wires every domain into a ``DomainRouter``.

All 12 PRD domains are now implemented (see BUILD_PROGRESS.md). Treasury/revenue/payables/
payroll/gst/tax/equity/compliance carry an 8-dim Mahsa sub-vector; ledger/forecast/expense/
vault have no sub-vector and are governed by their domain-scoped rules.
"""

from __future__ import annotations

from app.core.router import DomainRouter
from app.domains.compliance.service import ComplianceService
from app.domains.equity.service import EquityService
from app.domains.expense.service import ExpenseService
from app.domains.forecast.service import ForecastService
from app.domains.gst.service import GstService
from app.domains.ledger.service import LedgerService
from app.domains.payables.service import PayablesService
from app.domains.payroll.service import PayrollService
from app.domains.revenue.service import RevenueService
from app.domains.tax.service import TaxService
from app.domains.treasury.service import TreasuryService
from app.domains.vault.service import VaultService


def build_registry() -> DomainRouter:
    router = DomainRouter()
    router.register(TreasuryService())
    router.register(RevenueService())
    router.register(PayablesService())
    router.register(PayrollService())
    router.register(GstService())
    router.register(TaxService())
    router.register(LedgerService())
    router.register(ForecastService())
    router.register(EquityService())
    router.register(ComplianceService())
    router.register(ExpenseService())
    router.register(VaultService())
    return router
