/**
 * Expense computation core — pure, exact (integer paise), deterministic.
 * Faithful port of api/app/domains/expense/expense_calc.py.
 *
 * Covers per-category policy checks, the petty-cash threshold, mileage/per-diem,
 * category analytics, corporate-card reconciliation, and a receipt parser over OCR text.
 * The OCR image→text step (Tesseract) is the stubbed boundary; this parser works on text.
 * Money is integer paise throughout.
 */
import { paiseFromRupees } from '../../common/money';

/** Whole-day gap between two ISO 'YYYY-MM-DD' dates (matches Python date subtraction). */
function dayGap(a: string, b: string): number {
  return Math.round((Date.parse(a) - Date.parse(b)) / 86_400_000);
}

export type StatementLine = { id?: number; date: string; amount_paise: number };
export type ClaimLine = { id?: number; date: string; amount_paise: number };

export function reconcileCard(
  statementLines: StatementLine[],
  claims: ClaimLine[],
  opts: { dateToleranceDays?: number; amountTolerancePaise?: number } = {},
): {
  matched: { statement_id: number; claim_id: number; amount_paise: number }[];
  unmatched_statement: number[];
  unmatched_claims: number[];
  match_rate: number;
} {
  const dateTol = opts.dateToleranceDays ?? 3;
  const amtTol = opts.amountTolerancePaise ?? 0;

  const matched: { statement_id: number; claim_id: number; amount_paise: number }[] = [];
  const usedClaims = new Set<number>();
  const matchedStmt = new Set<number>();

  statementLines.forEach((s, si) => {
    const sAmount = Math.trunc(s.amount_paise);
    let bestCi: number | null = null;
    let bestGap: number | null = null;
    claims.forEach((c, ci) => {
      if (usedClaims.has(ci)) return;
      if (Math.abs(Math.trunc(c.amount_paise) - sAmount) > amtTol) return;
      const gap = Math.abs(dayGap(c.date, s.date));
      if (gap <= dateTol && (bestGap === null || gap < bestGap)) {
        bestCi = ci;
        bestGap = gap;
      }
    });
    if (bestCi !== null) {
      usedClaims.add(bestCi);
      matchedStmt.add(si);
      matched.push({
        statement_id: s.id ?? si,
        claim_id: claims[bestCi].id ?? bestCi,
        amount_paise: sAmount,
      });
    }
  });

  const round4 = (x: number) => Math.round(x * 10000) / 10000;
  const unmatchedStmt: number[] = [];
  statementLines.forEach((s, i) => {
    if (!matchedStmt.has(i)) unmatchedStmt.push(s.id ?? i);
  });
  const unmatchedClaims: number[] = [];
  claims.forEach((c, i) => {
    if (!usedClaims.has(i)) unmatchedClaims.push(c.id ?? i);
  });
  return {
    matched,
    unmatched_statement: unmatchedStmt,
    unmatched_claims: unmatchedClaims,
    match_rate: statementLines.length ? round4(matched.length / statementLines.length) : 1.0,
  };
}

// Default per-category reimbursement limits (paise).
export const DEFAULT_POLICY: Record<string, number> = {
  travel: paiseFromRupees(50000),
  meals: paiseFromRupees(2000),
  supplies: paiseFromRupees(10000),
  conveyance: paiseFromRupees(5000),
};

// PRD §1.11: petty cash imprest threshold.
export const PETTY_CASH_THRESHOLD = paiseFromRupees(10000);

const GSTIN_RE = /\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b/;
// currency-prefixed OR 2-decimal amount (avoids matching bare ints inside GSTIN/date).
const AMOUNT_RE = /(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)|([0-9][0-9,]*\.[0-9]{2})/gi;
const DATE_RE = /\b(\d{4}-\d{2}-\d{2}|\d{2}[/-]\d{2}[/-]\d{4})\b/;

export function checkPolicy(
  category: string,
  amount: number,
  limits?: Record<string, number>,
): { over_policy: boolean; limit: number | null; excess: number } {
  const table = limits ?? DEFAULT_POLICY;
  const limit = table[category];
  if (limit === undefined) {
    return { over_policy: false, limit: null, excess: 0 };
  }
  const excess = Math.max(0, Math.trunc(amount) - Math.trunc(limit));
  return { over_policy: excess > 0, limit: Math.trunc(limit), excess };
}

export function isPettyCashEligible(amount: number): boolean {
  return Math.trunc(amount) <= Math.trunc(PETTY_CASH_THRESHOLD);
}

export function mileageClaim(distanceKm: number, ratePerKm: number): number {
  return Math.trunc(distanceKm) * Math.trunc(ratePerKm);
}

export function perDiem(days: number, ratePerDay: number): number {
  return Math.trunc(days) * Math.trunc(ratePerDay);
}

export function categorySpend(claims: { category: string; amount: number }[]): Record<string, number> {
  const totals: Record<string, number> = {};
  for (const c of claims) {
    totals[c.category] = (totals[c.category] ?? 0) + Math.trunc(c.amount);
  }
  return totals;
}

export function parseReceipt(ocrText: string): {
  amount_paise: number | null;
  gstin: string | null;
  date: string | null;
} {
  const gstinMatch = ocrText.toUpperCase().match(GSTIN_RE);
  const dateMatch = ocrText.match(DATE_RE);

  const amounts: number[] = [];
  for (const m of ocrText.matchAll(AMOUNT_RE)) {
    const raw = (m[1] ?? m[2]).replace(/,/g, '');
    const paise = paiseFromRupees(raw);
    if (!Number.isNaN(paise)) amounts.push(paise);
  }
  const amountPaise = amounts.length ? Math.max(...amounts) : null;

  return {
    amount_paise: amountPaise,
    gstin: gstinMatch ? gstinMatch[0] : null,
    date: dateMatch ? dateMatch[0] : null,
  };
}
