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


def convertible_note_value(
    principal: int, *, annual_rate: float, months: int, compounding: str = "simple"
) -> dict[str, Any]:
    """Accrued value of a convertible note. ``annual_rate`` is a fraction (e.g. 0.08).
    ``simple``: principal × rate × months/12. ``monthly``: monthly compounding (exact Decimal)."""
    p = Decimal(int(principal))
    rate = Decimal(str(annual_rate))
    if compounding == "monthly":
        monthly = rate / Decimal(12)
        value = p
        for _ in range(max(0, int(months))):
            value *= Decimal(1) + monthly
        interest = value - p
    else:  # simple
        interest = p * rate * Decimal(int(months)) / Decimal(12)
    interest_paise = int(interest.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return {
        "principal": int(principal),
        "interest": interest_paise,
        "maturity_value": int(principal) + interest_paise,
    }


def share_certificates(holders: list[dict], *, default_form: str = "demat") -> list[dict]:
    """Allocate one share certificate per holder with contiguous distinctive share numbers
    (Companies (Share Capital and Debentures) Rules 2014, Rule 5). Each holder:
    {name, shares, form?}. ``form`` is 'demat' or 'physical'. Pure & deterministic."""
    certificates = []
    cursor = 1
    index = 0
    for h in holders:
        shares = int(h["shares"])
        if shares <= 0:
            continue
        index += 1
        certificates.append(
            {
                "certificate_no": f"SC-{index:04d}",
                "name": h["name"],
                "shares": shares,
                "distinctive_from": cursor,
                "distinctive_to": cursor + shares - 1,
                "form": h.get("form", default_form),
            }
        )
        cursor += shares
    return certificates


def rights_entitlement(holders: list[dict], new_shares: int) -> list[dict]:
    """Pro-rata rights-issue entitlement (Companies Act 2013 s.62(1)(a)): each existing
    holder may subscribe to ``new_shares`` in proportion to their current holding.
    Each holder: {name, shares}. Pure."""
    total = sum(int(h["shares"]) for h in holders)
    out = []
    for h in holders:
        held = int(h["shares"])
        entitlement = (held * int(new_shares)) // total if total > 0 else 0
        out.append({"name": h["name"], "shares": held, "entitlement": entitlement})
    return out


def buyback_compliance(
    *,
    paid_up_capital: int,
    free_reserves: int,
    buyback_amount: int,
    shares_bought_back: int = 0,
    total_shares: int = 0,
    post_buyback_debt: int = 0,
    post_buyback_equity: int = 0,
) -> dict[str, Any]:
    """Companies Act 2013 s.68 buyback limits: the buyback amount must not exceed 25% of
    (paid-up capital + free reserves), shares bought back must not exceed 25% of total equity,
    and the post-buyback debt:equity ratio must not exceed 2:1. All money in paise. Pure."""
    funds = int(paid_up_capital) + int(free_reserves)
    max_amount = funds // 4  # 25%
    amount_ok = int(buyback_amount) <= max_amount
    shares_ok = total_shares == 0 or int(shares_bought_back) <= int(total_shares) // 4
    ratio = (post_buyback_debt / post_buyback_equity) if post_buyback_equity else 0.0
    ratio_ok = ratio <= 2.0
    reasons = []
    if not amount_ok:
        reasons.append("buyback exceeds 25% of paid-up capital + free reserves")
    if not shares_ok:
        reasons.append("shares bought back exceed 25% of total equity")
    if not ratio_ok:
        reasons.append("post-buyback debt:equity exceeds 2:1")
    return {
        "permitted": amount_ok and shares_ok and ratio_ok,
        "max_amount": max_amount,
        "debt_equity_ratio": round(ratio, 4),
        "reasons": reasons,
    }


def dividend_distribution(
    *, distributable_profit: int, declared: int, shares: int
) -> dict[str, Any]:
    """Dividend declaration check (Companies Act 2013 s.123): a dividend may be declared only
    out of profits, so the declared amount must not exceed distributable profit. Returns whether
    it's permitted, the per-share amount (paise), and the profit remaining."""
    permitted = 0 <= declared <= distributable_profit
    payout = declared if permitted else 0
    per_share = payout // shares if shares > 0 and permitted else 0
    return {
        "permitted": permitted,
        "declared": payout,
        "per_share": per_share,
        "remaining_profit": int(distributable_profit) - payout,
    }
