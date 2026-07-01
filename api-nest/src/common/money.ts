/**
 * Exact money. TS mirror of api/app/core/money.py (which mirrors dif/src/money.rs).
 *
 * Money is integer paise (1 INR = 100 paise) end to end — never a float. JS numbers are
 * exact to 2^53 paise (≈ ₹90 trillion), far above any real figure. `moneyColumn` stores
 * paise as Postgres BIGINT but hands JS a `number` (not the string TypeORM defaults to),
 * so arithmetic stays numeric and exact.
 */
import { ColumnOptions } from 'typeorm';

const HUNDRED = 100;

/** Paise from a rupee amount, half-up (mirrors Decimal(str(x))*100 quantize ROUND_HALF_UP). */
export function paiseFromRupees(rupees: string | number): number {
  const d = typeof rupees === 'number' ? rupees : Number(rupees);
  const scaled = d * HUNDRED;
  return Math.sign(scaled) * Math.round(Math.abs(scaled));
}

/** Indian-grouped rupee string, e.g. ₹12,34,567.00. Display only — never money-math input. */
export function formatInr(paise: number): string {
  const sign = paise < 0 ? '-' : '';
  const whole = Math.floor(Math.abs(paise) / 100);
  const frac = Math.abs(paise) % 100;
  let s = String(whole);
  if (s.length > 3) {
    let head = s.slice(0, -3);
    const tail = s.slice(-3);
    const parts: string[] = [];
    while (head.length > 2) {
      parts.unshift(head.slice(-2));
      head = head.slice(0, -2);
    }
    if (head) parts.unshift(head);
    s = parts.join(',') + ',' + tail;
  }
  return `${sign}₹${s}.${String(frac).padStart(2, '0')}`;
}

/** BIGINT paise column that round-trips as a JS number. Use for every money column. */
export function moneyColumn(opts: ColumnOptions = {}): ColumnOptions {
  return {
    type: 'bigint',
    transformer: {
      to: (v: number | null) => v,
      from: (v: string | null) => (v === null || v === undefined ? v : Number(v)),
    },
    ...opts,
  };
}
