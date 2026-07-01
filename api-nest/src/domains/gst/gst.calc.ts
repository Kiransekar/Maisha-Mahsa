/**
 * GST computation core — pure, exact (integer paise), deterministic.
 * Faithful port of api/app/domains/gst/gst_calc.py. No clock is read; `daysLate`
 * is passed in. Re-verify rates/caps against the current Finance Act.
 *
 * Money is integer paise throughout — safe in JS numbers (well under 2^53).
 * Rupee rounding replicates Python's Decimal ROUND_HALF_UP (half away from zero);
 * interest uses integer arithmetic to avoid float 0.18 drift.
 */

import { createHash } from 'crypto';

export type TaxHeads = { igst: number; cgst: number; sgst: number };
const HEADS: (keyof TaxHeads)[] = ['igst', 'cgst', 'sgst'];

// ---- GSTIN validation ---------------------------------------------------------

const GSTIN_CODES = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;

export function gstinCheckDigit(first14: string): string {
  const mod = GSTIN_CODES.length;
  let factor = 2;
  let total = 0;
  for (const ch of [...first14].reverse()) {
    const code = GSTIN_CODES.indexOf(ch);
    let addend = factor * code;
    factor = factor === 2 ? 1 : 2;
    addend = Math.floor(addend / mod) + (addend % mod);
    total += addend;
  }
  return GSTIN_CODES[((mod - (total % mod)) % mod)];
}

export function validateGstin(gstin: unknown): boolean {
  if (typeof gstin !== 'string' || gstin.length !== 15 || !GSTIN_RE.test(gstin)) return false;
  const state = parseInt(gstin.slice(0, 2), 10);
  if (!(state >= 1 && state <= 38)) return false;
  return gstinCheckDigit(gstin.slice(0, 14)) === gstin[14];
}

// ---- ITC set-off --------------------------------------------------------------

function heads(d: Partial<TaxHeads>): TaxHeads {
  return { igst: ~~(d.igst ?? 0), cgst: ~~(d.cgst ?? 0), sgst: ~~(d.sgst ?? 0) };
}

export function itcSetoff(
  output: Partial<TaxHeads>,
  credit: Partial<TaxHeads>,
): { cash: TaxHeads; remaining_credit: TaxHeads } {
  const out = heads(output);
  const cr = heads(credit);
  const apply = (src: keyof TaxHeads, dst: keyof TaxHeads) => {
    const amt = Math.min(cr[src], out[dst]);
    cr[src] -= amt;
    out[dst] -= amt;
  };
  // Statutory order (Rule 88A): IGST credit first, then CGST, then SGST. CGST/SGST never cross.
  apply('igst', 'igst');
  apply('igst', 'cgst');
  apply('igst', 'sgst');
  apply('cgst', 'cgst');
  apply('cgst', 'igst');
  apply('sgst', 'sgst');
  apply('sgst', 'igst');
  return { cash: out, remaining_credit: cr };
}

// ---- GSTR-3B ------------------------------------------------------------------

const LATE_FEE_PER_DAY = 5000; // ₹50/day, paise
const LATE_FEE_PER_DAY_NIL = 2000; // ₹20/day
const LATE_FEE_CAP = 1_000_000; // ₹10,000
const LATE_FEE_CAP_NIL = 50_000; // ₹500

/** Round paise to the nearest rupee (half away from zero) and return paise. */
function roundRupee(paise: number): number {
  const p = Math.trunc(paise);
  const rupees = Math.sign(p) * Math.round(Math.abs(p) / 100);
  return rupees * 100;
}

export function lateFee3b(daysLate: number, isNil = false): number {
  if (daysLate <= 0) return 0;
  const perDay = isNil ? LATE_FEE_PER_DAY_NIL : LATE_FEE_PER_DAY;
  const cap = isNil ? LATE_FEE_CAP_NIL : LATE_FEE_CAP;
  return Math.min(perDay * Math.trunc(daysLate), cap);
}

export function interest3b(cashTax: number, daysLate: number): number {
  if (daysLate <= 0 || cashTax <= 0) return 0;
  // Decimal(cash) * 0.18 * days / 365, half-up to integer paise — via integers to stay exact.
  const num = Math.trunc(cashTax) * 18 * Math.trunc(daysLate);
  const interestPaise = Math.round(num / 36500); // 100 * 365; half-up for positive
  return roundRupee(interestPaise);
}

export function computeGstr3b(
  output: Partial<TaxHeads>,
  itcAvailable: Partial<TaxHeads>,
  opts: { daysLate?: number; isNil?: boolean } = {},
) {
  const daysLate = opts.daysLate ?? 0;
  const isNil = opts.isNil ?? false;
  const setoff = itcSetoff(output, itcAvailable);
  const cash = setoff.cash;
  const cashTotal = cash.igst + cash.cgst + cash.sgst;
  const fee = lateFee3b(daysLate, isNil);
  const interest = interest3b(cashTotal, daysLate);
  return {
    cash,
    cash_total: cashTotal,
    remaining_credit: setoff.remaining_credit,
    late_fee: fee,
    interest,
    total_payable: cashTotal + fee + interest,
  };
}

// ---- GSTR-1 outward summary ---------------------------------------------------

export type SupplyLine = {
  invoice_no?: string;
  taxable?: number;
  igst?: number;
  cgst?: number;
  sgst?: number;
  hsn?: string | null;
  gstin?: string | null;
  qty?: number;
};

export function buildGstr1(lines: SupplyLine[], filingPeriod: string) {
  const errors: string[] = [];
  const b2b: Record<string, any[]> = {};
  const b2c = { taxable: 0, igst: 0, cgst: 0, sgst: 0 };
  const hsn: Record<string, any> = {};

  lines.forEach((ln, i) => {
    const taxes = heads(ln);
    const taxable = ~~(ln.taxable ?? 0);
    const gstin = ln.gstin;
    const hsnCode = ln.hsn;

    if (!hsnCode) errors.push(`line ${i} (${ln.invoice_no ?? '?'}): missing HSN code`);

    if (gstin) {
      if (!validateGstin(gstin)) {
        errors.push(`line ${i} (${ln.invoice_no ?? '?'}): invalid GSTIN ${gstin}`);
      }
      (b2b[gstin] ??= []).push({ invoice_no: ln.invoice_no, taxable, ...taxes });
    } else {
      b2c.taxable += taxable;
      for (const h of HEADS) b2c[h] += taxes[h];
    }

    if (hsnCode) {
      const bucket = (hsn[hsnCode] ??= { taxable: 0, igst: 0, cgst: 0, sgst: 0, qty: 0 });
      bucket.taxable += taxable;
      bucket.qty += ~~(ln.qty ?? 0);
      for (const h of HEADS) bucket[h] += taxes[h];
    }
  });

  const totals: Record<string, number> = { taxable: 0, igst: 0, cgst: 0, sgst: 0 };
  for (const ln of lines) {
    totals.taxable += ~~(ln.taxable ?? 0);
    for (const h of HEADS) totals[h] += ~~(ln[h] ?? 0);
  }
  totals.total_tax = totals.igst + totals.cgst + totals.sgst;

  return { filing_period: filingPeriod, b2b, b2c, hsn, totals, errors };
}

// ---- Composition scheme -------------------------------------------------------

// Category levy rate as [percentNumerator] over 100 (s.10).
const COMPOSITION_PCT: Record<string, number> = {
  trader: 1,
  manufacturer: 1,
  restaurant: 5,
  service: 6,
};

export function compositionTax(turnover: number, category: string) {
  const pct = COMPOSITION_PCT[category];
  if (pct === undefined) throw new Error(`unknown composition category: ${category}`);
  const taxRaw = Math.trunc((Math.trunc(turnover) * pct) / 100); // int() truncation
  return {
    category,
    rate_pct: pct,
    turnover: Math.trunc(turnover),
    tax: roundRupee(taxRaw),
  };
}

// ---- e-Invoice IRN ------------------------------------------------------------

function einvoiceFy(isoDate: string): string {
  const [y, m] = isoDate.split('-').map((x) => parseInt(x, 10));
  const start = m >= 4 ? y : y - 1;
  return `${start}-${String(start + 1).slice(2)}`;
}

export function computeIrn(
  sellerGstin: string,
  opts: { docNo: string; docDate: string; docType?: string },
): string {
  const docType = opts.docType ?? 'INV';
  const fy = einvoiceFy(opts.docDate);
  const payload = `${sellerGstin.toUpperCase()}${fy}${docType.toUpperCase()}${opts.docNo}`;
  return createHash('sha256').update(payload).digest('hex');
}
