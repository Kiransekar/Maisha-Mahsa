// Indian lakh/crore grouping. Intl does this natively for en-IN — no formatting library, and
// no hand-rolled grouping regex to drift from the Python `format.py :: inr()` renderer.
// BRAND_THEME §4: money always renders grouped (₹12,34,567) and always with tabular numerals.
const FMT = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

/** Paise (integer, the only money type crossing the wire) -> "₹12,34,567". */
export function inr(paise: number): string {
  return FMT.format(Math.round(paise / 100));
}

/** For an amount that may legitimately be unknown. Never renders "₹0" for "we don't know". */
export function inrOrPending(paise: number | null | undefined): string {
  return paise === null || paise === undefined ? "—" : inr(paise);
}

// Indian-grouped plain counts (share counts, headcounts) — NOT money, no ₹. Lives here so the
// money-format grep-gate's invariant holds: every en-IN grouping in the SPA has one home.
const COUNT_FMT = new Intl.NumberFormat("en-IN");

/** Integer count -> "12,34,567" (Indian grouping, no currency symbol). */
export function countIn(n: number): string {
  return COUNT_FMT.format(n);
}
