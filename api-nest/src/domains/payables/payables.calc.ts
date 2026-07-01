/**
 * Payables computation core — pure, exact (integer paise), deterministic.
 * Faithful port of api/app/domains/payables/payables_calc.py.
 *
 * Covers the TDS-on-payments section engine (194C/194J/194H/194I) with rates + thresholds,
 * the PO↔GRN↔invoice 3-way match, AP aging, MSMED 45-day clock, early-payment discount and
 * recurring-vendor detection. TDS is on the taxable value (excl. GST, CBDT Circular 23/2017).
 * Time is injected via `asOf`. Money is integer paise; Python `Decimal ... ROUND_HALF_UP`
 * (half away from zero) is replicated with integer arithmetic to avoid float drift.
 *
 * Rates/thresholds are FY 2025-26 declared as data — re-verify each Finance Act.
 */

// ---- rounding helpers ---------------------------------------------------------

/** Half-up (away from zero for positive) integer division: round(num/den), num>=0, den>0. */
function roundHalfUpDiv(num: number, den: number): number {
  const q = Math.floor(num / den);
  const r = num - q * den;
  return 2 * r >= den ? q + 1 : q;
}

// ---- TDS on payments ----------------------------------------------------------

type TdsSection = {
  single: number; // per-transaction threshold, paise
  aggregate: number; // annual aggregate threshold, paise
  rate?: number;
  rate_individual?: number;
  rate_other?: number;
  rate_technical?: number;
  rate_plant?: number;
  rate_building?: number;
};

// section -> config. Rates in percent (integers).
const TDS_SECTIONS: Record<string, TdsSection> = {
  '194C': { rate_individual: 1, rate_other: 2, single: 30000_00, aggregate: 100000_00 },
  '194J': { rate: 10, rate_technical: 2, single: 30000_00, aggregate: 30000_00 },
  '194H': { rate: 2, single: 20000_00, aggregate: 20000_00 },
  '194I': { rate_plant: 2, rate_building: 10, single: 240000_00, aggregate: 240000_00 },
};

export const MSME_PAYMENT_DAYS = 45; // MSMED Act s.15

export function tdsRate(
  section: string,
  opts: { payee_type?: string; category?: string | null } = {},
): number {
  const cfg = TDS_SECTIONS[section];
  const payeeType = opts.payee_type ?? 'company';
  const category = opts.category ?? null;
  if (section === '194C') {
    return payeeType === 'individual' || payeeType === 'huf'
      ? cfg.rate_individual!
      : cfg.rate_other!;
  }
  if (section === '194J') return category === 'technical' ? cfg.rate_technical! : cfg.rate!;
  if (section === '194I') return category === 'plant' ? cfg.rate_plant! : cfg.rate_building!;
  return cfg.rate!;
}

export function tdsOnPayment(
  section: string,
  amount: number,
  opts: { payee_type?: string; category?: string | null; aggregate_ytd?: number } = {},
): { applicable: boolean; rate: number; tds_paise: number } {
  const cfg = TDS_SECTIONS[section];
  if (cfg === undefined) throw new Error(`unknown TDS section: ${section}`);
  amount = Math.trunc(amount);
  const aggregateYtd = opts.aggregate_ytd ?? 0;
  const applies = amount >= cfg.single || aggregateYtd + amount >= cfg.aggregate;
  if (!applies) return { applicable: false, rate: 0, tds_paise: 0 };
  const rate = tdsRate(section, opts);
  // Decimal(amount) * rate / 100, rounded to nearest rupee (half up): rupees = amount*rate/10000.
  const tds = roundHalfUpDiv(amount * rate, 10000) * 100;
  return { applicable: true, rate, tds_paise: tds };
}

// ---- 3-way match --------------------------------------------------------------

function variancePct(actual: number, expected: number): number {
  if (expected === 0) return actual === 0 ? 0 : 100;
  // abs(actual-expected)/expected*100, quantized to 2 dp half-up.
  const hundredths = roundHalfUpDiv(Math.abs(actual - expected) * 10000, expected);
  return hundredths / 100;
}

export function threeWayMatch(
  poAmount: number,
  billAmount: number,
  opts: { grn_amount?: number | null; tolerance_pct?: number } = {},
): {
  matched: boolean;
  po_variance_pct: number;
  grn_variance_pct: number;
  max_variance_pct: number;
} {
  const tol = opts.tolerance_pct ?? 5.0;
  const grnAmount = opts.grn_amount ?? null;
  const poVar = variancePct(billAmount, poAmount);
  const grnVar = grnAmount !== null ? variancePct(billAmount, grnAmount) : 0;
  return {
    matched: poVar <= tol && grnVar <= tol,
    po_variance_pct: poVar,
    grn_variance_pct: grnVar,
    max_variance_pct: Math.max(poVar, grnVar),
  };
}

// ---- AP aging -----------------------------------------------------------------

export const AGING_BUCKETS = ['0-30', '31-60', '61-90', '90+'] as const;

/** Whole calendar days between two 'YYYY-MM-DD' dates (later - earlier), UTC, no tz. */
function daysBetween(later: string, earlier: string): number {
  return Math.round((Date.parse(later) - Date.parse(earlier)) / 86_400_000);
}

export function agingBucket(daysOverdue: number): string {
  if (daysOverdue <= 30) return '0-30';
  if (daysOverdue <= 60) return '31-60';
  if (daysOverdue <= 90) return '61-90';
  return '90+';
}

export function apAging(
  payables: { due_date: string; outstanding_paise: number }[],
  asOf: string,
): { buckets: Record<string, number>; total_outstanding: number } {
  const buckets: Record<string, number> = { '0-30': 0, '31-60': 0, '61-90': 0, '90+': 0 };
  let total = 0;
  for (const p of payables) {
    const outstanding = Math.trunc(p.outstanding_paise);
    if (outstanding <= 0) continue;
    const days = daysBetween(asOf, p.due_date);
    buckets[agingBucket(days)] += outstanding;
    total += outstanding;
  }
  return { buckets, total_outstanding: total };
}

// ---- early-payment discount ---------------------------------------------------

export function earlyPaymentDiscount(
  invoiceAmount: number,
  opts: { discount_pct: number; discount_days: number; paid_in_days: number },
): { eligible: boolean; discount: number; net_payable: number } {
  const eligible = opts.paid_in_days <= opts.discount_days;
  // discount = round_rupee(amount * pct/100). rupees = amount*pctHundredths/1_000_000.
  // ponytail: discount_pct limited to 2 decimals (e.g. "2.5"); widen if sub-percent tiers appear.
  const pctHundredths = Math.round(opts.discount_pct * 100);
  const discount = eligible ? roundHalfUpDiv(invoiceAmount * pctHundredths, 1_000_000) * 100 : 0;
  return {
    eligible,
    discount,
    net_payable: Math.trunc(invoiceAmount) - discount,
  };
}

// ---- recurring-vendor detection -----------------------------------------------

function median(values: number[]): number {
  const s = [...values].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

function addDays(iso: string, days: number): string {
  const ms = Date.parse(iso) + days * 86_400_000;
  return new Date(ms).toISOString().slice(0, 10);
}

export type RecurringBill = {
  vendor_id: number | string;
  vendor_name?: string;
  bill_date: string;
  amount_paise: number;
};

export function detectRecurring(
  bills: RecurringBill[],
  opts: {
    min_occurrences?: number;
    gap_tolerance_days?: number;
    amount_tolerance_pct?: number;
  } = {},
): Record<string, any>[] {
  const minOccurrences = opts.min_occurrences ?? 3;
  const gapTol = opts.gap_tolerance_days ?? 7;
  const amountTol = opts.amount_tolerance_pct ?? 15.0;

  const byVendor = new Map<number | string, RecurringBill[]>();
  for (const b of bills) {
    const list = byVendor.get(b.vendor_id) ?? [];
    list.push(b);
    byVendor.set(b.vendor_id, list);
  }

  const out: Record<string, any>[] = [];
  for (const [vendorId, itemsRaw] of byVendor) {
    if (itemsRaw.length < minOccurrences) continue;
    const items = [...itemsRaw].sort((a, b) => (a.bill_date < b.bill_date ? -1 : 1));
    const dates = items.map((i) => i.bill_date);
    const gaps: number[] = [];
    for (let k = 1; k < dates.length; k++) gaps.push(daysBetween(dates[k], dates[k - 1]));
    const medianGap = median(gaps);
    if (!(28 - gapTol <= medianGap && medianGap <= 31 + gapTol)) continue;
    const amounts = items.map((i) => Math.trunc(i.amount_paise));
    const medianAmount = median(amounts);
    if (medianAmount <= 0) continue;
    const spreadPct =
      (Math.max(...amounts.map((a) => Math.abs(a - medianAmount))) / medianAmount) * 100;
    if (spreadPct > amountTol) continue;
    out.push({
      vendor_id: vendorId,
      vendor_name: items[items.length - 1].vendor_name ?? '',
      occurrences: items.length,
      median_gap_days: medianGap,
      predicted_amount_paise: medianAmount,
      predicted_next_date: addDays(dates[dates.length - 1], medianGap),
      category: 'saas_recurring',
    });
  }
  return out;
}
