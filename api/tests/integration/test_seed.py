"""P1-FIRSTRUN: the dev seed makes every headline KPI non-zero, and is idempotent."""

from __future__ import annotations

from datetime import date

from app.core.overview import collect_kpis
from app.dev.seed import already_seeded, seed


def test_seed_populates_nonzero_kpis(session):
    assert not already_seeded(session)
    result = seed(session)
    assert result["company"] == 1 and result["invoices"] == 2

    k = collect_kpis(session, date(2026, 6, 26))
    assert k["cash"] > 0, "treasury cash should be non-zero after seed"
    assert k["net_burn"] != 0, "burn should be non-zero (debits > credits)"
    assert k["ar"] > 0, "AR outstanding should be non-zero (unpaid invoices)"
    assert k["ap"] > 0, "AP outstanding should be non-zero (unpaid bills)"


def test_seed_is_idempotent(session):
    seed(session)
    assert seed(session) == {"skipped": 1}
    assert already_seeded(session)
