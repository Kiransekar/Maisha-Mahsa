"""Code on Wages 2019 s.2(y) — statutory wage base (MMX-1.0 §WS1.B1).

One definition of "wages" that every downstream levy (PF, ESI, gratuity, bonus, leave
encashment) must compute against, so a CTC that under-weights Basic can't shrink the statutory
base. Pure, exact integer paise.

s.2(y) (Code on Wages, 2019, Act 29 of 2019 — indiacode.nic.in aA2019-29.pdf, read verbatim):
  "wages" means ALL remuneration expressed in terms of money, and includes (i) basic pay,
  (ii) dearness allowance, (iii) retaining allowance — "but does not include" the CLOSED list of
  clauses (a)-(k): (a) statutory bonus outside the terms of employment; (b) house-accommodation /
  light / water / medical / amenity value; (c) employer PF or pension contribution; (d) conveyance
  allowance or travelling concession; (e) sums to defray special employment expenses; (f) HRA;
  (g) award/settlement remuneration; (h) overtime allowance; (i) commission; (j) gratuity on
  termination; (k) retrenchment compensation, other retirement benefit or termination ex gratia.
  FIRST PROVISO: "if payments made by the employer to the employee under clauses (a) to (i)
  exceeds one-half ... of the all remuneration calculated under this clause, the amount which
  exceeds such one-half ... shall be ... added in wages" — the add-back aggregates (a)-(i) ONLY;
  (j) and (k) are excluded from wages but sit OUTSIDE the add-back span (defect #5, fixed).

Classification decisions carried by the oracle vectors (ws1b_wage_base.yaml):
  * The exclusion list is CLOSED — a component not falling in (a)-(k) is remuneration and IS
    wages. Unknown keys are therefore INCLUDED (erring toward paying statutory dues), not
    silently excluded (defect #6, fixed). MoLE FAQ Sl.13 reads the other way and is recorded as
    an alternative in the vector; the statutory opening limb ("all remuneration") controls here.
  * special_allowance is INCLUDED: it appears nowhere in (a)-(k), and SC in RPFC (II) WB v.
    Vivekananda Vidyamandir (28-02-2019) holds allowances universally, necessarily and
    ordinarily paid to all employees form part of basic wages (defect #7; provenance=
    interpretation, ca_initials OWNER in the vector).
  * The proviso's denominator ("the all remuneration calculated under this clause") is read as
    ALL money components passed, including (j)/(k) — an interpretation recorded with
    alternatives in the vectors.

Interpretation flagged for CA confirmation (§0.7): the 15%-in-kind base is read here as 15% of the
money wage base after the add-back. This is opt-in (``in_kind`` defaults to 0), so the common path
is unaffected by the reading. Marked BLOCKED-CA below until initialled.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.core.money import Paise

# Components that ARE wages under the s.2(y) inclusion limb (i)-(iii).
INCLUDED_KEYS = ("basic", "da", "retaining_allowance")

# s.2(y) exclusion clauses (a)-(i) — the exact span the FIRST PROVISO aggregates for the add-back.
EXCLUDED_ADDBACK_KEYS = frozenset(
    {
        "bonus",
        "statutory_bonus",  # (a)
        "house_accommodation",
        "amenity_value",  # (b)
        "employer_pf",
        "employer_pension",  # (c)
        "conveyance",
        "travelling_concession",
        "lta",  # (d)
        "special_expenses_reimbursement",  # (e)
        "hra",  # (f)
        "award_settlement_remuneration",  # (g)
        "overtime",  # (h)
        "commission",  # (i)
    }
)
# Clauses (j)-(k): excluded from wages but OUTSIDE the proviso's (a)-(i) add-back span.
EXCLUDED_TERMINAL_KEYS = frozenset(
    {
        "gratuity",  # (j)
        "retrenchment_compensation",
        "retirement_benefit",
        "ex_gratia",  # (k)
    }
)

# The excluded-allowances share above which the excess is added back (s.2(y) first proviso).
EXCLUDED_CAP_FRACTION = Decimal("0.5")
# Remuneration-in-kind counts as wages up to this fraction of the wage base (s.2(y) explanation).
IN_KIND_CAP_FRACTION = Decimal("0.15")


def _round_paise(value: Decimal) -> int:
    return int(value.to_integral_value(ROUND_HALF_UP))


def statutory_wage_base(components: dict[str, int], *, in_kind: int = 0) -> Paise:
    """Monthly statutory wage base in paise from a component map (all values integer paise).

    Keys in ``INCLUDED_KEYS`` form the inclusion limb; keys in ``EXCLUDED_ADDBACK_KEYS`` are the
    clause (a)-(i) exclusions the first proviso aggregates; keys in ``EXCLUDED_TERMINAL_KEYS`` are
    clauses (j)-(k) (excluded, outside the add-back span). Any OTHER key is remuneration not in
    the closed exclusion list and is counted as wages. ``in_kind`` is the money value of
    remuneration in kind.
    """
    included = excluded_addback = excluded_terminal = 0
    for k, v in components.items():
        if k in EXCLUDED_ADDBACK_KEYS:
            excluded_addback += int(v)
        elif k in EXCLUDED_TERMINAL_KEYS:
            excluded_terminal += int(v)
        else:
            # Inclusion limb, or a component outside the closed (a)-(k) list -> wages.
            included += int(v)
    total_remuneration = included + excluded_addback + excluded_terminal

    base = Decimal(included)
    # First proviso: add back the clause (a)-(i) excess over 50% of all remuneration.
    cap = Decimal(total_remuneration) * EXCLUDED_CAP_FRACTION
    if Decimal(excluded_addback) > cap:
        base += Decimal(excluded_addback) - cap

    # Remuneration-in-kind counts up to 15% of the wage base (interpretation: BLOCKED-CA §0.7).
    if in_kind > 0:
        countable = min(Decimal(int(in_kind)), base * IN_KIND_CAP_FRACTION)
        base += countable

    return Paise(_round_paise(base))
