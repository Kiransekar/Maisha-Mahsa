/**
 * Faithfulness check: every expected value here was produced by the Python reference
 * (api/app/domains/ledger/ledger_calc.py). If the TS port drifts, this fails.
 */
import * as l from './ledger.calc';

describe('ledger.calc — parity with Python reference', () => {
  it('is_balanced', () => {
    expect(l.isBalanced([{ debit: 10000, credit: 0 }, { debit: 0, credit: 10000 }])).toBe(true);
    expect(l.isBalanced([{ debit: 10000 }, { credit: 9000 }])).toBe(false);
  });

  it('trial_balance', () => {
    expect(
      l.trialBalance([
        { debit: 10000, credit: 0 },
        { debit: 0, credit: 7000 },
        { debit: 0, credit: 3000 },
      ]),
    ).toEqual({ total_debit: 10000, total_credit: 10000, diff: 0, balanced: true });
  });

  const rows: l.TypedRow[] = [
    { account_type: 'income', debit: 0, credit: 500000 },
    { account_type: 'expense', debit: 300000, credit: 0 },
    { account_type: 'asset', debit: 800000, credit: 0 },
    { account_type: 'liability', debit: 0, credit: 400000 },
    { account_type: 'equity', debit: 0, credit: 200000 },
  ];

  it('profit_and_loss', () => {
    expect(l.profitAndLoss(rows)).toEqual({ income: 500000, expense: 300000, net_profit: 200000 });
  });

  it('balance_sheet (accounting equation)', () => {
    expect(l.balanceSheet(rows)).toEqual({
      assets: 800000,
      liabilities: 400000,
      equity: 200000,
      retained_profit: 200000,
      balanced: true,
    });
  });

  it('depreciation — SLM (ROUND_HALF_UP to whole rupee)', () => {
    expect(l.slmAnnual(10000000, 1000000, 5)).toBe(1800000);
    expect(l.slmAnnual(10000033, 0, 3)).toBe(3333300);
    expect(l.slmAnnual(1000, 0, 0)).toBe(0);
  });

  it('depreciation — WDV (integer-exact rate)', () => {
    expect(l.wdvAnnual(10000000, 13.91)).toBe(1391000);
    expect(l.wdvAnnual(5000055, 15.0)).toBe(750000);
  });

  it('bank_reconciliation', () => {
    expect(
      l.bankReconciliation(100000, 90000, { deposits_in_transit: 15000, unpresented_cheques: 5000 }),
    ).toEqual({
      book_balance: 100000,
      adjusted_bank_balance: 100000,
      difference: 0,
      reconciled: true,
    });
  });

  it('payroll_journal (balanced by construction)', () => {
    expect(
      l.payrollJournal({
        salary_expense_account: 1,
        bank_account: 2,
        statutory_payable_account: 3,
        gross: 100000,
        net: 80000,
        statutory: 20000,
      }),
    ).toEqual([
      { account_id: 1, debit: 100000, credit: 0, description: 'Payroll — gross salary' },
      { account_id: 2, debit: 0, credit: 80000, description: 'Payroll — net pay' },
      { account_id: 3, debit: 0, credit: 20000, description: 'Payroll — statutory payable' },
    ]);
    expect(() =>
      l.payrollJournal({
        salary_expense_account: 1,
        bank_account: 2,
        statutory_payable_account: 3,
        gross: 100000,
        net: 80000,
        statutory: 10000,
      }),
    ).toThrow();
  });

  it('sales_journal', () => {
    expect(
      l.salesJournal({
        receivable_account: 1,
        sales_account: 2,
        gst_output_account: 3,
        taxable: 100000,
        tax: 18000,
      }),
    ).toEqual([
      { account_id: 1, debit: 118000, credit: 0, description: 'Invoice — receivable' },
      { account_id: 2, debit: 0, credit: 100000, description: 'Invoice — sales' },
      { account_id: 3, debit: 0, credit: 18000, description: 'Invoice — GST output' },
    ]);
  });

  it('gst_payment_journal', () => {
    expect(l.gstPaymentJournal({ gst_payable_account: 1, bank_account: 2, amount: 18000 })).toEqual([
      { account_id: 1, debit: 18000, credit: 0, description: 'GST payment' },
      { account_id: 2, debit: 0, credit: 18000, description: 'GST payment — bank' },
    ]);
  });
});
