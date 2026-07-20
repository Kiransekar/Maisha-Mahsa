"""Tax: ITR-5/6 computation and transfer-pricing checks (features itr / transfer_pricing)."""

from app.core.money import Paise
from app.domains.tax import tax_calc as t


def test_itr6_company_115baa_effective_rate_and_mat_excluded():
    # §WS1.C4: 115BAA = 22% + 10% surcharge + 4% cess = 25.168% effective; MAT excluded.
    res = t.itr_computation(
        entity_type="company",
        gross_total_income=Paise.from_rupees(10_000_000),
        deductions=Paise.from_rupees(0),
        book_profit=Paise.from_rupees(10_000_000),
        tds_paid=Paise.from_rupees(500_000),
        advance_tax_paid=Paise.from_rupees(1_000_000),
    )
    assert res["form"] == "ITR-6"
    assert res["normal_tax"] == Paise.from_rupees(2_516_800)  # 25.168% of 1 crore
    assert res["mat"] == 0  # MAT excluded on the 115BAA path
    assert res["tax_payable"] == res["normal_tax"]
    assert res["balance_payable"] == res["tax_payable"] - Paise.from_rupees(1_500_000)


def test_itr6_non_115baa_is_blocked_ca():
    import pytest

    with pytest.raises(NotImplementedError):
        t.itr_computation(
            entity_type="company",
            gross_total_income=Paise.from_rupees(10_000_000),
            regime_115baa=False,
        )


def test_itr5_firm_form_and_rate():
    res = t.itr_computation(
        entity_type="llp", gross_total_income=Paise.from_rupees(1_000_000)
    )
    assert res["form"] == "ITR-5" and res["mat"] == 0
    # 30% + 4% cess on 10L
    assert res["normal_tax"] == Paise.from_rupees(312000)


def test_itr_refund_when_prepaid_exceeds_tax():
    res = t.itr_computation(
        entity_type="company", gross_total_income=Paise.from_rupees(1_000_000),
        tds_paid=Paise.from_rupees(900_000),
    )
    assert res["refund_due"] > 0 and res["balance_payable"] == 0


def test_arms_length_within_and_outside_range():
    comps = [Paise.from_rupees(100), Paise.from_rupees(102), Paise.from_rupees(98)]  # mean 100
    inside = t.arms_length_check(Paise.from_rupees(101), comps)  # within +/-3%
    assert inside["at_arms_length"] is True and inside["adjustment"] == 0
    outside = t.arms_length_check(Paise.from_rupees(120), comps)
    assert outside["at_arms_length"] is False
    assert outside["adjustment"] == outside["arms_length_price"] - Paise.from_rupees(120)
    assert t.arms_length_check(Paise.from_rupees(100), [])["at_arms_length"] is None


def test_tp_documentation_thresholds():
    none = t.tp_documentation_required(intl_transaction_value=0)
    assert none["form_3ceb_required"] is False
    small = t.tp_documentation_required(intl_transaction_value=Paise.from_rupees(5_000_000))
    assert small["form_3ceb_required"] is True and small["rule_10d_documentation"] is False
    big = t.tp_documentation_required(
        intl_transaction_value=Paise.from_rupees(50_000_000),  # > 1 cr
        group_consolidated_revenue=Paise.from_rupees(6000 * 10**7),  # > 5500 cr
    )
    assert big["rule_10d_documentation"] is True
    assert big["master_file_required"] is True and big["cbcr_required"] is True
