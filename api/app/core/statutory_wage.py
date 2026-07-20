"""Code on Wages 2019 s.2(y) — statutory wage base (MMX-1.0 §WS1.B1).

One definition of "wages" that every downstream levy (PF, ESI, gratuity, bonus, leave
encashment) must compute against, so a CTC that under-weights Basic can't shrink the statutory
base. Pure, exact integer paise.

The s.2(y) rule, as stated in the spec:
  1. wages = Basic + Dearness Allowance + retaining allowance.
  2. Excluded components (HRA, conveyance, overtime, commission, bonus, employer PF, …) are left
     out — BUT if their total exceeds 50% of the total remuneration, the excess over 50% is added
     back into wages (the anti-avoidance proviso; overtime is counted in the excluded total here).
  3. Remuneration in kind is counted as wages up to 15%.

Interpretation flagged for CA confirmation (§0.7): the 15%-in-kind base is read here as 15% of the
money wage base after the add-back. This is opt-in (``in_kind`` defaults to 0), so the common path
— (1)+(2) — is unaffected by the reading. Marked BLOCKED-CA below until initialled.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.core.money import Paise

# Components that ARE wages under s.2(y) limb (a). Everything else the caller passes is "excluded".
INCLUDED_KEYS = ("basic", "da", "retaining_allowance")

# The excluded-allowances share above which the excess is added back (s.2(y) second proviso).
EXCLUDED_CAP_FRACTION = Decimal("0.5")
# Remuneration-in-kind counts as wages up to this fraction of the wage base (s.2(y) explanation).
IN_KIND_CAP_FRACTION = Decimal("0.15")


def _round_paise(value: Decimal) -> int:
    return int(value.to_integral_value(ROUND_HALF_UP))


def statutory_wage_base(components: dict[str, int], *, in_kind: int = 0) -> Paise:
    """Monthly statutory wage base in paise from a component map (all values integer paise).

    ``components`` keys in ``INCLUDED_KEYS`` form the narrow base; every other key is an excluded
    allowance (overtime included). ``in_kind`` is the money value of remuneration in kind.
    """
    included = sum(int(components.get(k, 0)) for k in INCLUDED_KEYS)
    excluded = sum(int(v) for k, v in components.items() if k not in INCLUDED_KEYS)
    total_remuneration = included + excluded

    base = Decimal(included)
    # Second proviso: add back the excluded excess over 50% of total remuneration.
    cap = Decimal(total_remuneration) * EXCLUDED_CAP_FRACTION
    if Decimal(excluded) > cap:
        base += Decimal(excluded) - cap

    # Remuneration-in-kind counts up to 15% of the wage base (interpretation: BLOCKED-CA §0.7).
    if in_kind > 0:
        countable = min(Decimal(int(in_kind)), base * IN_KIND_CAP_FRACTION)
        base += countable

    return Paise(_round_paise(base))
