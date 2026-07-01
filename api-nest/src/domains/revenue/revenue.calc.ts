/**
 * Revenue computation core — pure, exact (integer paise), deterministic.
 * Faithful port of api/app/domains/revenue/revenue_calc.py. No clock is read;
 * `asOf` is passed in as an ISO date string.
 *
 * Money is integer paise throughout. Rupee/paise rounding replicates Python's
 * Decimal ROUND_HALF_UP (half away from zero) using integer arithmetic to avoid
 * float drift on rates like 18.0 / 5.0 / 12.5.
 */

// ---- rational rounding helpers ------------------------------------------------

/** Represent a decimal rate as an exact integer fraction (mirrors Decimal(str(x))). */
function rateFraction(rate: number): { num: number; den: number } {
  const s = String(rate);
  const dot = s.indexOf('.');
  const decimals = dot < 0 ? 0 : s.length - dot - 1;
  const den = Math.pow(10, decimals);
  return { num: Math.round(rate * den), den };
}

/** round(|num|/den) half away from zero, integers in, integer paise out. */
function roundDiv(num: number, den: number): number {
  const sign = num < 0 ? -1 : 1;
  const a = Math.abs(num);
  return sign * Math.floor((a * 2 + den) / (den * 2));
}

/** Half-up round of subtotal * rate / divisor, exact via integer fraction. */
function roundRate(subtotal: number, rate: number, divisor: number): number {
  const { num, den } = rateFraction(rate);
  return roundDiv(subtotal * num, divisor * den);
}

// ---- invoicing ----------------------------------------------------------------

export type InvoiceLineInput = { quantity: number | string; rate: number | string };

export function computeInvoice(
  items: InvoiceLineInput[],
  opts: { gstRate: number; interState: boolean; tdsRate?: number },
): {
  subtotal: number;
  igst_amount: number;
  cgst_amount: number;
  sgst_amount: number;
  total_tax: number;
  total_amount: number;
  tds_amount: number;
  net_receivable: number;
} {
  const tdsRate = opts.tdsRate ?? 0;
  const subtotal = items.reduce(
    (s, it) => s + Math.trunc(Number(it.quantity)) * Math.trunc(Number(it.rate)),
    0,
  );

  let igst = 0;
  let cgst = 0;
  let sgst = 0;
  if (opts.interState) {
    igst = roundRate(subtotal, opts.gstRate, 100);
  } else {
    cgst = roundRate(subtotal, opts.gstRate, 200);
    sgst = cgst;
  }
  const totalTax = igst + cgst + sgst;
  const totalAmount = subtotal + totalTax;

  const tdsAmount = roundRate(subtotal, tdsRate, 100);
  const netReceivable = totalAmount - tdsAmount;

  return {
    subtotal,
    igst_amount: igst,
    cgst_amount: cgst,
    sgst_amount: sgst,
    total_tax: totalTax,
    total_amount: totalAmount,
    tds_amount: tdsAmount,
    net_receivable: netReceivable,
  };
}

// ---- AR aging -----------------------------------------------------------------

export const AGING_BUCKETS = ['0-30', '31-60', '61-90', '90+'] as const;
export type AgingBucket = (typeof AGING_BUCKETS)[number];

export function agingBucket(daysOverdue: number): AgingBucket {
  if (daysOverdue <= 30) return '0-30';
  if (daysOverdue <= 60) return '31-60';
  if (daysOverdue <= 90) return '61-90';
  return '90+';
}

function daysBetween(laterIso: string, earlierIso: string): number {
  const ms = Date.parse(laterIso) - Date.parse(earlierIso);
  return Math.round(ms / 86_400_000);
}

export function arAging(
  receivables: { due_date: string; outstanding_paise: number }[],
  asOf: string,
): { buckets: Record<AgingBucket, number>; total_outstanding: number } {
  const buckets: Record<AgingBucket, number> = {
    '0-30': 0,
    '31-60': 0,
    '61-90': 0,
    '90+': 0,
  };
  let total = 0;
  for (const r of receivables) {
    const outstanding = Math.trunc(Number(r.outstanding_paise));
    if (outstanding <= 0) continue;
    const days = daysBetween(asOf, r.due_date);
    buckets[agingBucket(days)] += outstanding;
    total += outstanding;
  }
  return { buckets, total_outstanding: total };
}

// ---- dunning ------------------------------------------------------------------

const DUNNING_SCHEDULE: [number, string][] = [
  [-7, 'T-7'],
  [-3, 'T-3'],
  [-1, 'T-1'],
  [1, 'T+1'],
  [7, 'T+7'],
];

/** Reminder labels that fall exactly on `asOf` for an invoice with this due date. */
export function dunningDue(dueDate: string, asOf: string): string[] {
  const delta = daysBetween(dueDate, asOf); // (due - as_of).days
  return DUNNING_SCHEDULE.filter(([offset]) => delta === -offset).map(([, label]) => label);
}

// ---- credit notes (CGST s.34) -------------------------------------------------

/** 30 November following the FY (Apr–Mar) of the original supply. */
export function creditNoteDeadline(invoiceDate: string): string {
  const [y, mo] = invoiceDate.split('-').map((x) => parseInt(x, 10));
  const fyFollowing = mo >= 4 ? y + 1 : y;
  return `${fyFollowing}-11-30`;
}

export function isCreditNoteTimely(invoiceDate: string, cnDate: string): boolean {
  return cnDate <= creditNoteDeadline(invoiceDate);
}

// ---- exports (IGST s.16 zero-rated) -------------------------------------------

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

export function exportInvoice(
  taxable: number,
  opts: { withLut: boolean; igstRate?: number; invoiceDate: string },
): {
  zero_rated: boolean;
  with_lut: boolean;
  igst: number;
  total: number;
  refund_eligible: boolean;
  realization_due_date: string;
} {
  const igstRate = opts.igstRate ?? 18.0;
  const t = Math.trunc(taxable);
  const igst = opts.withLut ? 0 : roundRate(t, igstRate, 100);
  const [iy, im, id] = opts.invoiceDate.split('-').map((x) => parseInt(x, 10));
  const months = im - 1 + 9;
  const year = iy + Math.floor(months / 12);
  const month = (months % 12) + 1;
  const day = Math.min(id, daysInMonth(year, month));
  const realization = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  return {
    zero_rated: true,
    with_lut: opts.withLut,
    igst,
    total: t + igst,
    refund_eligible: !opts.withLut && igst > 0,
    realization_due_date: realization,
  };
}

// ---- deferred revenue ---------------------------------------------------------

export function deferredRevenueSchedule(
  total: number,
  opts: { start: string; months: number; asOf: string },
): { total: number; monthly: number; months_elapsed: number; recognized: number; deferred: number } {
  const { start, months, asOf } = opts;
  if (months <= 0) throw new Error('months must be positive');
  const [sy, sm] = start.split('-').map((x) => parseInt(x, 10));
  const [ay, am] = asOf.split('-').map((x) => parseInt(x, 10));
  let elapsed = (ay - sy) * 12 + (am - sm);
  elapsed = Math.max(0, Math.min(months, elapsed));
  const t = Math.trunc(total);
  const monthly = roundDiv(t, months);
  const recognized = elapsed >= months ? t : Math.min(t, monthly * elapsed);
  return {
    total: t,
    monthly,
    months_elapsed: elapsed,
    recognized,
    deferred: t - recognized,
  };
}
