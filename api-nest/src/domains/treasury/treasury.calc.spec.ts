/**
 * Faithfulness check: every expected value here was produced by the Python
 * reference (api/app/domains/treasury/service.py). If the TS port drifts, this fails.
 */
import * as t from './treasury.calc';

describe('treasury.calc — parity with Python reference', () => {
  it('parseDate — all accepted formats + rejects', () => {
    expect(t.parseDate('2024-05-15')).toBe('2024-05-15');
    expect(t.parseDate('15/05/2024')).toBe('2024-05-15');
    expect(t.parseDate('15/05/24')).toBe('2024-05-15');
    expect(t.parseDate('15-05-2024')).toBe('2024-05-15');
    expect(t.parseDate('15-May-2024')).toBe('2024-05-15');
    expect(t.parseDate('15 May 2024')).toBe('2024-05-15');
    expect(t.parseDate('5/5/2024')).toBe('2024-05-05');
    expect(t.parseDate('31/02/2024')).toBeNull(); // invalid day for month
    expect(t.parseDate('garbage')).toBeNull();
    expect(t.parseDate('01-Jan-70')).toBeNull(); // %b needs a 4-digit year
    expect(t.parseDate('15-June-2024')).toBeNull(); // %b needs the 3-letter abbrev
  });

  it('parseAmount — cleaning + ROUND_HALF_UP to paise', () => {
    expect(t.parseAmount('1,234.56')).toBe(123456);
    expect(t.parseAmount('₹500.00')).toBe(50000);
    expect(t.parseAmount('Rs.1000')).toBe(100000);
    expect(t.parseAmount('-')).toBe(0);
    expect(t.parseAmount('')).toBe(0);
    expect(t.parseAmount('0.00')).toBe(0);
    expect(t.parseAmount('1234')).toBe(123400);
    expect(t.parseAmount('abc')).toBe(0);
    expect(t.parseAmount('12,34,567.89')).toBe(123456789);
  });

  it('monthsBack — day clamped to month length', () => {
    expect(t.monthsBack('2024-03-31', 1)).toBe('2024-02-29');
    expect(t.monthsBack('2024-03-31', 2)).toBe('2024-01-31');
    expect(t.monthsBack('2024-03-31', 3)).toBe('2023-12-31');
    expect(t.monthsBack('2024-03-31', 13)).toBe('2023-02-28');
    expect(t.monthsBack('2024-01-15', 1)).toBe('2023-12-15');
  });

  it('sweepSuggestion', () => {
    expect(t.sweepSuggestion(100000000, 5000000, 6)).toEqual({
      cash: 100000000,
      buffer_months: 6,
      buffer_required: 30000000,
      sweepable: 70000000,
      recommend_sweep: true,
    });
    expect(t.sweepSuggestion(1000, 5000)).toEqual({
      cash: 1000,
      buffer_months: 6,
      buffer_required: 30000,
      sweepable: 0,
      recommend_sweep: false,
    });
  });

  it('upiReconcile', () => {
    expect(
      t.upiReconcile(
        [
          { reference: 'a', amount: 100 },
          { reference: 'b', amount: 200 },
        ],
        [
          { reference: 'a', amount: 100 },
          { reference: 'c', amount: 300 },
        ],
      ),
    ).toEqual({
      matched: ['a'],
      unmatched_upi: ['c'],
      unmatched_bank: ['b'],
      reconciled: false,
    });
  });

  it('bankGuaranteeStatus', () => {
    expect(t.bankGuaranteeStatus('2024-06-15', '2024-06-01')).toEqual({
      expiry_date: '2024-06-15',
      days_to_expiry: 14,
      expired: false,
      renewal_due: true,
    });
    expect(t.bankGuaranteeStatus('2024-05-15', '2024-06-01')).toEqual({
      expiry_date: '2024-05-15',
      days_to_expiry: -17,
      expired: true,
      renewal_due: false,
    });
  });

  it('resolveColumns — header mapping + priority', () => {
    expect(
      t.resolveColumns([
        'Txn Date',
        'Narration',
        'Chq./Ref.No.',
        'Withdrawal Amt',
        'Deposit Amt',
        'Closing Balance',
      ]),
    ).toEqual({ date: 0, description: 1, reference: 2, debit: 3, credit: 4, balance: 5 });
    expect(t.resolveColumns(['Date', 'Description', 'Debit', 'Credit'])).toEqual({
      date: 0,
      description: 1,
      debit: 2,
      credit: 3,
    });
    expect(() => t.resolveColumns(['Foo', 'Bar'])).toThrow();
  });

  it('cashPositionFrom + metricsFrom — burn / runway / share', () => {
    const cash = t.cashPositionFrom({ HDFC: 60000000, ICICI: 40000000 });
    expect(cash).toEqual({
      total_cash_paise: 100000000,
      account_count: 2,
      largest_account_share: 0.6,
      by_account: { HDFC: 60000000, ICICI: 40000000 },
    });
    expect(t.metricsFrom(cash, 30000000, 9000000)).toEqual({
      window_months: 3,
      cash_paise: 100000000,
      monthly_burn_paise: 10000000,
      monthly_revenue_paise: 3000000,
      net_burn_paise: 7000000,
      runway_months: 14.29,
      largest_account_share: 0.6,
      account_count: 2,
    });
    // not burning -> runway is null (infinite)
    const cash3 = t.cashPositionFrom({ Only: 50000000 });
    expect(t.metricsFrom(cash3, 12000000, 15000000)).toMatchObject({
      net_burn_paise: 0,
      runway_months: null,
      largest_account_share: 1.0,
    });
    // empty
    expect(t.cashPositionFrom({})).toEqual({
      total_cash_paise: 0,
      account_count: 0,
      largest_account_share: 0.0,
      by_account: {},
    });
  });

  it('pyRound — banker rounding on ties', () => {
    expect(t.pyRound(2.5)).toBe(2);
    expect(t.pyRound(3.5)).toBe(4);
    expect(t.pyRound(2.675, 2)).toBe(2.67); // float-repr, matches Python round(2.675,2)
  });
});
