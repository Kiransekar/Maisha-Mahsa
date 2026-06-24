"""Golden eval cases, aggregated. Add a domain by writing ``cases/<domain>.py`` exposing a
module-level ``CASES: list[EvalCase]`` and importing it here. P0-① ships treasury + gst;
the remaining ten domains follow in P0-①b (see P0_HARNESS_PLAN.md sequencing)."""

from __future__ import annotations

from ..types import EvalCase
from . import (
    compliance,
    equity,
    expense,
    forecast,
    gst,
    ledger,
    payables,
    payroll,
    revenue,
    tax,
    treasury,
    vault,
)

ALL_CASES: list[EvalCase] = [
    *treasury.CASES,
    *revenue.CASES,
    *payables.CASES,
    *payroll.CASES,
    *gst.CASES,
    *tax.CASES,
    *ledger.CASES,
    *forecast.CASES,
    *equity.CASES,
    *compliance.CASES,
    *expense.CASES,
    *vault.CASES,
]
