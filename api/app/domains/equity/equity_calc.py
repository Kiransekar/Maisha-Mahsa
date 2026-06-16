"""Cap-table & equity computation core — pure, deterministic. Share counts are integers;
money (investment, valuation, price) is integer paise.

Covers ownership %, the ESOP-pool ratio, SAFE-note conversion (valuation cap vs discount —
the better-for-investor price wins), and round dilution.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def ownership(holders: list[dict]) -> dict[str, Any]:
    """Aggregate a cap table. ``holders`` are {category, shares}. Returns total shares,
    shares by category, and ownership fraction by category (sums to 1.0 when shares > 0)."""
    total = sum(int(h["shares"]) for h in holders)
    by_category: dict[str, int] = {}
    for h in holders:
        by_category[h["category"]] = by_category.get(h["category"], 0) + int(h["shares"])
    pct = {
        cat: round(shares / total, 6) if total > 0 else 0.0 for cat, shares in by_category.items()
    }
    return {"total_shares": total, "by_category": by_category, "pct": pct}


def esop_pool_pct(pool_shares: int, total_diluted_shares: int) -> float:
    if total_diluted_shares <= 0:
        return 0.0
    return round(int(pool_shares) / int(total_diluted_shares), 6)


def safe_conversion(
    *,
    investment: int,
    valuation_cap: int | None,
    discount_rate: float,
    round_price_per_share: int,
    pre_round_shares: int,
) -> dict[str, int]:
    """Convert a SAFE at a priced round. Conversion price = min(cap price, discount price)
    — whichever gives the investor more shares. All prices in paise/share."""
    candidates: list[int] = []
    if valuation_cap and pre_round_shares > 0:
        candidates.append(int(valuation_cap) // int(pre_round_shares))  # cap price
    if discount_rate:
        disc = Decimal(int(round_price_per_share)) * (Decimal(1) - Decimal(str(discount_rate)))
        candidates.append(int(disc.to_integral_value(ROUND_HALF_UP)))
    if not candidates:
        candidates.append(int(round_price_per_share))

    conversion_price = max(1, min(candidates))
    shares = int(investment) // conversion_price  # whole shares only
    return {"conversion_price_paise": conversion_price, "shares_issued": shares}


def post_round_ownership(holder_shares: int, pre_total_shares: int, new_shares: int) -> float:
    """Ownership fraction of a holder after ``new_shares`` are issued in a round."""
    new_total = int(pre_total_shares) + int(new_shares)
    return round(int(holder_shares) / new_total, 6) if new_total > 0 else 0.0
