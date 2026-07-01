/**
 * Double-entry accounting core — pure, exact (integer paise), deterministic.
 * Faithful port of api/app/domains/ledger/ledger_calc.py.
 *
 * Money is integer paise throughout (safe in JS numbers, well under 2^53).
 * Rupee rounding replicates Python's Decimal ROUND_HALF_UP (half away from zero);
 * all division is done in integer arithmetic to avoid float drift.
 * Normal balances: asset/expense are debit-natured; liability/equity/income are credit-natured.
 */

export const DEBIT_NATURED = ['asset', 'expense'] as const;
export const CREDIT_NATURED = ['liability', 'equity', 'income'] as const;

export type Line = { debit?: number; credit?: number };
export type TypedRow = { account_type: string; debit?: number; credit?: number };
export type JournalLineOut = {
  account_id: number;
  debit: number;
  credit: number;
  description: string;
};

/** Integer half-away-from-zero of n/d (d>0), matching Decimal ROUND_HALF_UP on rupees. */
function divRoundHalfUp(n: number, d: number): number {
  const sign = n < 0 ? -1 : 1;
  const a = Math.abs(n);
  return sign * Math.floor((2 * a + d) / (2 * d));
}

export function isBalanced(lines: Line[]): boolean {
  const dr = lines.reduce((s, ln) => s + ~~(ln.debit ?? 0), 0);
  const cr = lines.reduce((s, ln) => s + ~~(ln.credit ?? 0), 0);
  return dr === cr;
}

export function trialBalance(lines: Line[]) {
  const totalDebit = lines.reduce((s, ln) => s + ~~(ln.debit ?? 0), 0);
  const totalCredit = lines.reduce((s, ln) => s + ~~(ln.credit ?? 0), 0);
  return {
    total_debit: totalDebit,
    total_credit: totalCredit,
    diff: totalDebit - totalCredit,
    balanced: totalDebit === totalCredit,
  };
}

function netByNature(rows: TypedRow[], accountType: string): number {
  const debitNatured = (DEBIT_NATURED as readonly string[]).includes(accountType);
  let total = 0;
  for (const r of rows) {
    if (r.account_type !== accountType) continue;
    const debit = ~~(r.debit ?? 0);
    const credit = ~~(r.credit ?? 0);
    total += debitNatured ? debit - credit : credit - debit;
  }
  return total;
}

export function profitAndLoss(rows: TypedRow[]) {
  const income = netByNature(rows, 'income');
  const expense = netByNature(rows, 'expense');
  return { income, expense, net_profit: income - expense };
}

export function balanceSheet(rows: TypedRow[]) {
  const assets = netByNature(rows, 'asset');
  const liabilities = netByNature(rows, 'liability');
  const equity = netByNature(rows, 'equity');
  const netProfit = profitAndLoss(rows).net_profit;
  return {
    assets,
    liabilities,
    equity,
    retained_profit: netProfit,
    balanced: assets === liabilities + equity + netProfit,
  };
}

/** Straight-line depreciation per year = (cost − salvage) / life, rounded to whole rupee. */
export function slmAnnual(cost: number, salvage: number, usefulLifeYears: number): number {
  if (usefulLifeYears <= 0) return 0;
  const rupees = divRoundHalfUp(~~cost - ~~salvage, usefulLifeYears * 100);
  return rupees * 100;
}

/**
 * WDV depreciation for one year = opening WDV × rate%, rounded to whole rupee.
 * rate_pct is a JS number; String(rate_pct) mirrors Python str()→Decimal(str), so we
 * parse its decimal digits to keep integer arithmetic exact (no float 13.91 drift).
 */
export function wdvAnnual(openingWdv: number, ratePct: number): number {
  const s = String(ratePct);
  const [intPart, fracPart = ''] = s.replace('-', '').split('.');
  const k = fracPart.length;
  const numRate = parseInt((intPart + fracPart) || '0', 10) * (s.startsWith('-') ? -1 : 1);
  // paise = openingWdv * ratePct / 100; rupees = paise / 100 = openingWdv*numRate / (10^k * 10000)
  const denom = Math.pow(10, k) * 10000;
  const rupees = divRoundHalfUp(~~openingWdv * numRate, denom);
  return rupees * 100;
}

export function bankReconciliation(
  bookBalance: number,
  bankStatementBalance: number,
  opts: { deposits_in_transit?: number; unpresented_cheques?: number } = {},
) {
  const deposits = ~~(opts.deposits_in_transit ?? 0);
  const unpresented = ~~(opts.unpresented_cheques ?? 0);
  const adjusted = ~~bankStatementBalance + deposits - unpresented;
  const difference = ~~bookBalance - adjusted;
  return {
    book_balance: ~~bookBalance,
    adjusted_bank_balance: adjusted,
    difference,
    reconciled: difference === 0,
  };
}

// ── auto-posting: balanced journal-line builders for cross-module source events ──────

export function payrollJournal(args: {
  salary_expense_account: number;
  bank_account: number;
  statutory_payable_account: number;
  gross: number;
  net: number;
  statutory: number;
}): JournalLineOut[] {
  if (~~args.net + ~~args.statutory !== ~~args.gross) {
    throw new Error('payroll journal: net + statutory must equal gross');
  }
  return [
    { account_id: args.salary_expense_account, debit: ~~args.gross, credit: 0, description: 'Payroll — gross salary' },
    { account_id: args.bank_account, debit: 0, credit: ~~args.net, description: 'Payroll — net pay' },
    { account_id: args.statutory_payable_account, debit: 0, credit: ~~args.statutory, description: 'Payroll — statutory payable' },
  ];
}

export function salesJournal(args: {
  receivable_account: number;
  sales_account: number;
  gst_output_account: number;
  taxable: number;
  tax: number;
}): JournalLineOut[] {
  return [
    { account_id: args.receivable_account, debit: ~~args.taxable + ~~args.tax, credit: 0, description: 'Invoice — receivable' },
    { account_id: args.sales_account, debit: 0, credit: ~~args.taxable, description: 'Invoice — sales' },
    { account_id: args.gst_output_account, debit: 0, credit: ~~args.tax, description: 'Invoice — GST output' },
  ];
}

export function gstPaymentJournal(args: {
  gst_payable_account: number;
  bank_account: number;
  amount: number;
}): JournalLineOut[] {
  return [
    { account_id: args.gst_payable_account, debit: ~~args.amount, credit: 0, description: 'GST payment' },
    { account_id: args.bank_account, debit: 0, credit: ~~args.amount, description: 'GST payment — bank' },
  ];
}
