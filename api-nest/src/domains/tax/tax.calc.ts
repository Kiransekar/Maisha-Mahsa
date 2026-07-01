/**
 * Direct-tax computation core — pure, exact (integer paise), deterministic.
 * Faithful port of api/app/domains/tax/tax_calc.py.
 *
 * Covers advance-tax schedule + s.234C deferment interest (with the 12%/36% relief
 * provisos), s.234B, s.234E TDS-return late fee, s.44AB tax-audit trigger, MAT (s.115JB),
 * ITR headline, transfer pricing, 26AS reconciliation, s.80-IAC tax holiday.
 * Rates/thresholds are FY 2025-26 (AY 2026-27); re-verify each Finance Act.
 *
 * Money is integer paise throughout. Python `Decimal ... ROUND_HALF_UP` (half away from zero)
 * is replicated with exact BigInt arithmetic so there is zero float drift on money.
 */

// Round half away from zero for the rational a/b (b > 0). BigInt = exact.
function divRoundHalfAway(a: bigint, b: bigint): bigint {
  const neg = a < 0n;
  const aa = neg ? -a : a;
  const q = (2n * aa + b) / (2n * b); // floor(aa/b + 1/2) = round-half-up for non-negative
  return neg ? -q : q;
}

/**
 * Python `_round_rupee(paise)`: round the (possibly fractional) paise value paiseNum/paiseDen
 * to the nearest rupee half-away-from-zero, and return integer paise. Exact via BigInt.
 */
function roundRupeeExact(paiseNum: bigint, paiseDen: bigint): number {
  const rupees = divRoundHalfAway(paiseNum, paiseDen * 100n);
  return Number(rupees * 100n);
}

const B = (n: number): bigint => BigInt(Math.trunc(n));

// s.234C installments: cumulative % (×100), relief-floor % (×100), months of interest.
// Q1/Q2 carry the statutory relief (no interest if >=12%/36% paid); Q3/Q4 do not.
type Installment = { label: string; pctNum: number; floorNum: number; months: number };
const ADVANCE_TAX_SCHEDULE: Installment[] = [
  { label: 'Q1', pctNum: 15, floorNum: 12, months: 3 },
  { label: 'Q2', pctNum: 45, floorNum: 36, months: 3 },
  { label: 'Q3', pctNum: 75, floorNum: 75, months: 3 },
  { label: 'Q4', pctNum: 100, floorNum: 100, months: 1 },
];

const _234E_PER_DAY = 20000; // Paise.from_rupees(200)

// s.44AB thresholds (paise)
const AUDIT_BUSINESS = 1_000_000_000; // ₹1 Cr
const AUDIT_BUSINESS_DIGITAL = 10_000_000_000; // ₹10 Cr (cash ≤ 5%)
const AUDIT_PROFESSIONAL = 500_000_000; // ₹50 L

const ONE_CRORE_PAISE = 10 ** 7 * 100; // 1e9
const RULE_10D_THRESHOLD = ONE_CRORE_PAISE; // ₹1 Cr aggregate international transactions
const MASTER_FILE_THRESHOLD = 500 * ONE_CRORE_PAISE; // ₹500 Cr group revenue
const CBCR_THRESHOLD = 5500 * ONE_CRORE_PAISE; // ₹5500 Cr group revenue (s.286)

// ---- advance tax / s.234C -----------------------------------------------------

export function advanceTaxSchedule(totalLiability: number): Array<{ installment: string; cumulative_required: number }> {
  const liab = B(totalLiability);
  return ADVANCE_TAX_SCHEDULE.map(({ label, pctNum }) => ({
    installment: label,
    // paise = liability * pctNum / 100
    cumulative_required: roundRupeeExact(liab * BigInt(pctNum), 100n),
  }));
}

export function interest234c(
  totalLiability: number,
  cumulativePaid: number[],
): { total_234c: number; by_installment: Record<string, number> } {
  if (cumulativePaid.length !== 4) {
    throw new Error('cumulative_paid must have 4 entries (Q1..Q4)');
  }
  const liab = B(totalLiability);
  let total = 0;
  const byInstallment: Record<string, number> = {};
  ADVANCE_TAX_SCHEDULE.forEach(({ label, pctNum, floorNum, months }, i) => {
    const paid = B(cumulativePaid[i]);
    // relief: Decimal(paid) >= liability*floorNum/100  ⟺  100*paid >= liability*floorNum
    if (100n * paid >= liab * BigInt(floorNum)) {
      byInstallment[label] = 0;
      return;
    }
    // shortfall = liability*pctNum/100 - paid; interest = round_rupee(shortfall * 0.01 * months)
    // paise = (liability*pctNum - 100*paid) * months / (100 * 100)
    const paiseNum = (liab * BigInt(pctNum) - 100n * paid) * BigInt(months);
    const interest = roundRupeeExact(paiseNum, 10000n);
    byInstallment[label] = interest;
    total += interest;
  });
  return { total_234c: total, by_installment: byInstallment };
}

export function interest234b(
  assessedTax: number,
  advancePaid: number,
  months: number,
): { applicable: boolean; shortfall: number; interest: number; months: number } {
  if (assessedTax <= 0 || months <= 0) {
    return { applicable: false, shortfall: 0, interest: 0, months };
  }
  // advance_paid >= assessed * 0.9  ⟺  10*advance_paid >= 9*assessed
  if (10 * advancePaid >= 9 * assessedTax) {
    return { applicable: false, shortfall: 0, interest: 0, months };
  }
  let shortfall = Math.max(0, assessedTax - advancePaid);
  shortfall = Math.trunc(shortfall / 10000) * 10000; // round down to nearest ₹100 (10,000 paise)
  // interest = round_rupee(shortfall * 0.01 * months) => paise = shortfall*months/100
  const interest = roundRupeeExact(B(shortfall) * B(months), 100n);
  return { applicable: true, shortfall, interest, months };
}

// ---- s.234E TDS-return late fee -----------------------------------------------

export function lateFee234e(daysLate: number, tdsAmount: number): number {
  if (daysLate <= 0) return 0;
  return Math.min(_234E_PER_DAY * Math.trunc(daysLate), Math.trunc(tdsAmount));
}

// ---- s.80-IAC tax holiday -----------------------------------------------------

export function taxHolidayDeduction(
  profit: number,
  claimedYears: number,
  eligible: boolean,
): { eligible: boolean; deduction: number; taxable_after_holiday: number; holiday_years_remaining: number } {
  const available = eligible && profit > 0 && claimedYears < 3;
  const deduction = available ? Math.trunc(profit) : 0;
  return {
    eligible: available,
    deduction,
    taxable_after_holiday: Math.trunc(profit) - deduction,
    holiday_years_remaining: Math.max(0, 3 - claimedYears - (available ? 1 : 0)),
  };
}

// ---- 26AS reconciliation ------------------------------------------------------

type TanEntry = { tan: string; amount: number };

export function reconcile26as(
  books: TanEntry[],
  as26as: TanEntry[],
): {
  matched: Array<{ tan: string; amount: number }>;
  mismatched: Array<{ tan: string; books: number; as_26as: number; variance: number }>;
  missing_in_26as: Array<{ tan: string; books: number }>;
  missing_in_books: Array<{ tan: string; as_26as: number }>;
  reconciled: boolean;
} {
  const bookByTan = new Map<string, number>();
  const deptByTan = new Map<string, number>();
  for (const e of books) bookByTan.set(e.tan, (bookByTan.get(e.tan) ?? 0) + Math.trunc(e.amount));
  for (const e of as26as) deptByTan.set(e.tan, (deptByTan.get(e.tan) ?? 0) + Math.trunc(e.amount));

  const matched: Array<{ tan: string; amount: number }> = [];
  const mismatched: Array<{ tan: string; books: number; as_26as: number; variance: number }> = [];
  const missing_in_26as: Array<{ tan: string; books: number }> = [];
  const missing_in_books: Array<{ tan: string; as_26as: number }> = [];

  const tans = [...new Set([...bookByTan.keys(), ...deptByTan.keys()])].sort();
  for (const tan of tans) {
    const bv = bookByTan.get(tan);
    const dv = deptByTan.get(tan);
    if (dv === undefined) {
      missing_in_26as.push({ tan, books: bv as number });
    } else if (bv === undefined) {
      missing_in_books.push({ tan, as_26as: dv });
    } else if (bv === dv) {
      matched.push({ tan, amount: bv });
    } else {
      mismatched.push({ tan, books: bv, as_26as: dv, variance: bv - dv });
    }
  }
  return {
    matched,
    mismatched,
    missing_in_26as,
    missing_in_books,
    reconciled: mismatched.length === 0 && missing_in_26as.length === 0 && missing_in_books.length === 0,
  };
}

// ---- s.44AB tax-audit trigger -------------------------------------------------

export function auditRequired(
  turnover: number,
  opts: { cashRatio?: number; isProfessional?: boolean } = {},
): boolean {
  const cashRatio = opts.cashRatio ?? 0.0;
  if (opts.isProfessional) return turnover > AUDIT_PROFESSIONAL;
  if (turnover > AUDIT_BUSINESS_DIGITAL) return true;
  return turnover > AUDIT_BUSINESS && cashRatio > 0.05;
}

// ---- ITR headline computation -------------------------------------------------

const COMPANY_RATE_NUM = 2288; // 0.22 * 1.04 * 10000 (s.115BAA 22% + 4% cess)
const FIRM_RATE_NUM = 3120; // 0.30 * 1.04 * 10000 (LLP / firm)

export function itrComputation(args: {
  entityType: string;
  grossTotalIncome: number;
  deductions?: number;
  bookProfit?: number | null;
  tdsPaid?: number;
  advanceTaxPaid?: number;
}): {
  form: string;
  entity_type: string;
  total_income: number;
  normal_tax: number;
  mat: number;
  tax_payable: number;
  prepaid_taxes: number;
  balance_payable: number;
  refund_due: number;
} {
  const et = args.entityType.toLowerCase();
  const totalIncome = Math.max(0, Math.trunc(args.grossTotalIncome) - Math.trunc(args.deductions ?? 0));
  const isCompany = et === 'company';
  const form = isCompany ? 'ITR-6' : 'ITR-5';
  const rateNum = isCompany ? COMPANY_RATE_NUM : FIRM_RATE_NUM;
  // normal_tax = round_rupee(total_income * rate * 1.04) => paise = total_income*rateNum/10000
  const normalTax = roundRupeeExact(B(totalIncome) * BigInt(rateNum), 10000n);
  const bp = args.bookProfit;
  const mat = isCompany && bp !== null && bp !== undefined ? matLiability(Math.trunc(bp)) : 0;
  const taxPayable = Math.max(normalTax, mat);
  const prepaid = Math.trunc(args.tdsPaid ?? 0) + Math.trunc(args.advanceTaxPaid ?? 0);
  return {
    form,
    entity_type: et,
    total_income: totalIncome,
    normal_tax: normalTax,
    mat,
    tax_payable: taxPayable,
    prepaid_taxes: prepaid,
    balance_payable: Math.max(0, taxPayable - prepaid),
    refund_due: Math.max(0, prepaid - taxPayable),
  };
}

// ---- transfer pricing ---------------------------------------------------------

export function armsLengthCheck(
  price: number,
  comparables: number[],
  tolerancePct = 3.0,
):
  | { at_arms_length: null; reason: string }
  | { at_arms_length: boolean; arms_length_price: number; lower: number; upper: number; adjustment: number } {
  if (comparables.length === 0) {
    return { at_arms_length: null, reason: 'no comparables provided' };
  }
  const sum = comparables.reduce((s, c) => s + Math.trunc(c), 0);
  const mean = Math.floor(sum / comparables.length); // Python // (floor)
  // band = int(Decimal(mean) * tol / 100)  — truncate toward zero.
  // ponytail: float tol matches Python Decimal(str(tol)) for ordinary percentages; exotic
  //           tolerances with long decimals could drift — swap to a rational if that matters.
  const band = Math.trunc((mean * tolerancePct) / 100);
  const lower = mean - band;
  const upper = mean + band;
  const atArmsLength = lower <= Math.trunc(price) && Math.trunc(price) <= upper;
  return {
    at_arms_length: atArmsLength,
    arms_length_price: mean,
    lower,
    upper,
    adjustment: atArmsLength ? 0 : mean - Math.trunc(price),
  };
}

export function tpDocumentationRequired(args: {
  intlTransactionValue: number;
  groupConsolidatedRevenue?: number;
}): {
  form_3ceb_required: boolean;
  rule_10d_documentation: boolean;
  master_file_required: boolean;
  cbcr_required: boolean;
} {
  const intl = Math.trunc(args.intlTransactionValue);
  const group = Math.trunc(args.groupConsolidatedRevenue ?? 0);
  return {
    form_3ceb_required: intl > 0,
    rule_10d_documentation: intl > RULE_10D_THRESHOLD,
    master_file_required: group > MASTER_FILE_THRESHOLD,
    cbcr_required: group > CBCR_THRESHOLD,
  };
}

// ---- MAT (s.115JB) ------------------------------------------------------------

export function matLiability(bookProfit: number): number {
  if (bookProfit <= 0) return 0;
  // 15% of book profit + 4% cess => paise = book_profit * 1560 / 10000
  return roundRupeeExact(B(bookProfit) * 1560n, 10000n);
}
