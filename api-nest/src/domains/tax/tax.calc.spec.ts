/**
 * Faithfulness check: every expected value here was produced by the Python
 * reference (api/app/domains/tax/tax_calc.py). If the TS port drifts, this fails.
 */
import * as t from './tax.calc';

describe('tax.calc — parity with Python reference', () => {
  it('advance-tax cumulative schedule', () => {
    expect(t.advanceTaxSchedule(10_000_000_000)).toEqual([
      { installment: 'Q1', cumulative_required: 1_500_000_000 },
      { installment: 'Q2', cumulative_required: 4_500_000_000 },
      { installment: 'Q3', cumulative_required: 7_500_000_000 },
      { installment: 'Q4', cumulative_required: 10_000_000_000 },
    ]);
  });

  it('s.234C deferment interest', () => {
    expect(t.interest234c(10_000_000_000, [0, 0, 0, 0])).toEqual({
      total_234c: 505_000_000,
      by_installment: { Q1: 45_000_000, Q2: 135_000_000, Q3: 225_000_000, Q4: 100_000_000 },
    });
    // fully paid to relief floors → no interest
    expect(t.interest234c(10_000_000_000, [1_500_000_000, 4_500_000_000, 7_500_000_000, 10_000_000_000])).toEqual({
      total_234c: 0,
      by_installment: { Q1: 0, Q2: 0, Q3: 0, Q4: 0 },
    });
    expect(t.interest234c(10_000_000_000, [1_000_000_000, 3_000_000_000, 5_000_000_000, 9_000_000_000])).toEqual({
      total_234c: 145_000_000,
      by_installment: { Q1: 15_000_000, Q2: 45_000_000, Q3: 75_000_000, Q4: 10_000_000 },
    });
    expect(() => t.interest234c(1000, [0, 0, 0])).toThrow();
  });

  it('s.234B assessed-tax interest', () => {
    expect(t.interest234b(10_000_000_000, 5_000_000_000, 6)).toEqual({
      applicable: true,
      shortfall: 5_000_000_000,
      interest: 300_000_000,
      months: 6,
    });
    // advance tax >= 90% assessed → not applicable
    expect(t.interest234b(10_000_000_000, 9_500_000_000, 6)).toEqual({
      applicable: false,
      shortfall: 0,
      interest: 0,
      months: 6,
    });
  });

  it('s.234E TDS-return late fee (₹200/day, capped at TDS)', () => {
    expect(t.lateFee234e(30, 100_000_000)).toBe(600_000);
    expect(t.lateFee234e(30, 500_000)).toBe(500_000); // capped at TDS amount
    expect(t.lateFee234e(0, 100_000)).toBe(0);
  });

  it('s.80-IAC tax holiday', () => {
    expect(t.taxHolidayDeduction(5_000_000, 1, true)).toEqual({
      eligible: true,
      deduction: 5_000_000,
      taxable_after_holiday: 0,
      holiday_years_remaining: 1,
    });
    expect(t.taxHolidayDeduction(5_000_000, 3, true)).toEqual({
      eligible: false,
      deduction: 0,
      taxable_after_holiday: 5_000_000,
      holiday_years_remaining: 0,
    });
  });

  it('s.44AB tax-audit trigger', () => {
    expect(t.auditRequired(1_050_000_000, { cashRatio: 0.1 })).toBe(true);
    expect(t.auditRequired(1_050_000_000, { cashRatio: 0.01 })).toBe(false);
    expect(t.auditRequired(6_000_000, { isProfessional: true })).toBe(false);
  });

  it('MAT liability (s.115JB, 15% + 4% cess)', () => {
    expect(t.matLiability(10_000_000_000)).toBe(1_560_000_000);
    expect(t.matLiability(0)).toBe(0);
  });

  it('ITR headline computation', () => {
    expect(
      t.itrComputation({
        entityType: 'company',
        grossTotalIncome: 10_000_000_000,
        deductions: 1_000_000_000,
        bookProfit: 8_000_000_000,
        tdsPaid: 500_000_000,
        advanceTaxPaid: 500_000_000,
      }),
    ).toEqual({
      form: 'ITR-6',
      entity_type: 'company',
      total_income: 9_000_000_000,
      normal_tax: 2_059_200_000,
      mat: 1_248_000_000,
      tax_payable: 2_059_200_000,
      prepaid_taxes: 1_000_000_000,
      balance_payable: 1_059_200_000,
      refund_due: 0,
    });
    expect(t.itrComputation({ entityType: 'firm', grossTotalIncome: 10_000_000_000 })).toEqual({
      form: 'ITR-5',
      entity_type: 'firm',
      total_income: 10_000_000_000,
      normal_tax: 3_120_000_000,
      mat: 0,
      tax_payable: 3_120_000_000,
      prepaid_taxes: 0,
      balance_payable: 3_120_000_000,
      refund_due: 0,
    });
  });

  it('transfer-pricing arm’s-length test', () => {
    expect(t.armsLengthCheck(1_000_000, [980_000, 1_010_000, 1_020_000], 3.0)).toEqual({
      at_arms_length: true,
      arms_length_price: 1_003_333,
      lower: 973_234,
      upper: 1_033_432,
      adjustment: 0,
    });
    expect(t.armsLengthCheck(1_000_000, [1_200_000, 1_300_000, 1_400_000])).toEqual({
      at_arms_length: false,
      arms_length_price: 1_300_000,
      lower: 1_261_000,
      upper: 1_339_000,
      adjustment: 300_000,
    });
    expect(t.armsLengthCheck(1000, [])).toEqual({ at_arms_length: null, reason: 'no comparables provided' });
  });

  it('transfer-pricing documentation thresholds', () => {
    expect(t.tpDocumentationRequired({ intlTransactionValue: 200_000_000, groupConsolidatedRevenue: 600_000_000_000 })).toEqual({
      form_3ceb_required: true,
      rule_10d_documentation: false,
      master_file_required: true,
      cbcr_required: false,
    });
  });

  it('Form 26AS reconciliation', () => {
    expect(
      t.reconcile26as(
        [
          { tan: 'A', amount: 1000 },
          { tan: 'B', amount: 2000 },
        ],
        [
          { tan: 'A', amount: 1000 },
          { tan: 'B', amount: 2500 },
          { tan: 'C', amount: 300 },
        ],
      ),
    ).toEqual({
      matched: [{ tan: 'A', amount: 1000 }],
      mismatched: [{ tan: 'B', books: 2000, as_26as: 2500, variance: -500 }],
      missing_in_26as: [],
      missing_in_books: [{ tan: 'C', as_26as: 300 }],
      reconciled: false,
    });
  });
});
