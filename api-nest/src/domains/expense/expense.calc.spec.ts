/**
 * Faithfulness check: every expected value here was produced by the Python
 * reference (api/app/domains/expense/expense_calc.py). If the TS port drifts, this fails.
 */
import * as e from './expense.calc';

describe('expense.calc — parity with Python reference', () => {
  it('default policy + petty-cash thresholds (paise)', () => {
    expect(e.DEFAULT_POLICY).toEqual({
      travel: 5000000,
      meals: 200000,
      supplies: 1000000,
      conveyance: 500000,
    });
    expect(e.PETTY_CASH_THRESHOLD).toBe(1000000);
  });

  it('check_policy — over / under / unknown category', () => {
    expect(e.checkPolicy('travel', 6000000)).toEqual({ over_policy: true, limit: 5000000, excess: 1000000 });
    expect(e.checkPolicy('travel', 4000000)).toEqual({ over_policy: false, limit: 5000000, excess: 0 });
    expect(e.checkPolicy('random', 999999)).toEqual({ over_policy: false, limit: null, excess: 0 });
  });

  it('petty-cash eligibility (≤ ₹10,000)', () => {
    expect(e.isPettyCashEligible(1000000)).toBe(true);
    expect(e.isPettyCashEligible(1000001)).toBe(false);
  });

  it('mileage + per-diem (paise)', () => {
    expect(e.mileageClaim(150, 1200)).toBe(180000);
    expect(e.perDiem(5, 250000)).toBe(1250000);
  });

  it('category spend totals', () => {
    expect(
      e.categorySpend([
        { category: 'travel', amount: 500 },
        { category: 'meals', amount: 200 },
        { category: 'travel', amount: 300 },
      ]),
    ).toEqual({ travel: 800, meals: 200 });
  });

  it('receipt parsing — amount/gstin/date', () => {
    expect(e.parseReceipt('Total: Rs 1,234.56 GSTIN 27AAPFU0939F1ZV Date 2024-05-15')).toEqual({
      amount_paise: 123456,
      gstin: '27AAPFU0939F1ZV',
      date: '2024-05-15',
    });
    expect(e.parseReceipt('no money here just 27AAPFU0939F1ZV and 2024-01-02')).toEqual({
      amount_paise: null,
      gstin: '27AAPFU0939F1ZV',
      date: '2024-01-02',
    });
    expect(e.parseReceipt('Subtotal 100.00 Tax 18.00 Total 118.00')).toEqual({
      amount_paise: 11800,
      gstin: null,
      date: null,
    });
  });

  it('corporate-card reconciliation (greedy, nearest date)', () => {
    expect(
      e.reconcileCard(
        [
          { id: 1, date: '2024-05-10', amount_paise: 50000 },
          { id: 2, date: '2024-05-12', amount_paise: 30000 },
          { id: 3, date: '2024-05-20', amount_paise: 99999 },
        ],
        [
          { id: 101, date: '2024-05-11', amount_paise: 50000 },
          { id: 102, date: '2024-05-13', amount_paise: 30000 },
        ],
      ),
    ).toEqual({
      matched: [
        { statement_id: 1, claim_id: 101, amount_paise: 50000 },
        { statement_id: 2, claim_id: 102, amount_paise: 30000 },
      ],
      unmatched_statement: [3],
      unmatched_claims: [],
      match_rate: 0.6667,
    });
  });
});
