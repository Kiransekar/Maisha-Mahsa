/**
 * Cap-table & equity computation core — pure, exact, deterministic. Faithful port of
 * api/app/domains/equity/equity_calc.py.
 *
 * Share counts are integers; money (investment, valuation, price) is integer paise.
 * Python `Decimal ... ROUND_HALF_UP` = round half away from zero — replicated with integer
 * arithmetic (see roundHalfUpDiv) to avoid float drift. `round(x, n)` fractions use round6/round4.
 */

const round6 = (x: number): number => Math.round(x * 1e6) / 1e6;
const round4 = (x: number): number => Math.round(x * 1e4) / 1e4;

/** Half away from zero for a positive rational num/den (both positive integers). */
function roundHalfUpDiv(num: number, den: number): number {
  const q = Math.floor(num / den);
  const r = num - q * den;
  return 2 * r >= den ? q + 1 : q;
}

/** Decimal(str(rate)) as an exact integer fraction, mirroring Python's shortest-repr string. */
function rateFraction(rate: number): { num: number; den: number } {
  const s = String(rate);
  const dot = s.indexOf('.');
  if (dot === -1) return { num: parseInt(s, 10), den: 1 };
  const decimals = s.length - dot - 1;
  return { num: parseInt(s.replace('.', ''), 10), den: Math.pow(10, decimals) };
}

// ---- cap table ----------------------------------------------------------------

export type Holder = { category: string; shares: number };

export function ownership(holders: Holder[]): {
  total_shares: number;
  by_category: Record<string, number>;
  pct: Record<string, number>;
} {
  const total = holders.reduce((s, h) => s + Math.trunc(h.shares), 0);
  const by_category: Record<string, number> = {};
  for (const h of holders) by_category[h.category] = (by_category[h.category] ?? 0) + Math.trunc(h.shares);
  const pct: Record<string, number> = {};
  for (const [cat, shares] of Object.entries(by_category)) pct[cat] = total > 0 ? round6(shares / total) : 0.0;
  return { total_shares: total, by_category, pct };
}

export function esopPoolPct(poolShares: number, totalDilutedShares: number): number {
  if (totalDilutedShares <= 0) return 0.0;
  return round6(Math.trunc(poolShares) / Math.trunc(totalDilutedShares));
}

// ---- SAFE ---------------------------------------------------------------------

export function safeConversion(args: {
  investment: number;
  valuation_cap: number | null;
  discount_rate: number;
  round_price_per_share: number;
  pre_round_shares: number;
}): { conversion_price_paise: number; shares_issued: number } {
  const { investment, valuation_cap, discount_rate, round_price_per_share, pre_round_shares } = args;
  const candidates: number[] = [];
  if (valuation_cap && pre_round_shares > 0) {
    candidates.push(Math.floor(valuation_cap / pre_round_shares)); // cap price
  }
  if (discount_rate) {
    const { num, den } = rateFraction(discount_rate);
    // disc = round_price * (1 - rate) = round_price * (den - num) / den, half-up to int paise.
    candidates.push(roundHalfUpDiv(round_price_per_share * (den - num), den));
  }
  if (candidates.length === 0) candidates.push(round_price_per_share);

  const conversion_price = Math.max(1, Math.min(...candidates));
  const shares = Math.floor(investment / conversion_price); // whole shares only
  return { conversion_price_paise: conversion_price, shares_issued: shares };
}

export function postRoundOwnership(holderShares: number, preTotalShares: number, newShares: number): number {
  const newTotal = preTotalShares + newShares;
  return newTotal > 0 ? round6(holderShares / newTotal) : 0.0;
}

// ---- convertible note ---------------------------------------------------------

export function convertibleNoteValue(
  principal: number,
  opts: { annual_rate: number; months: number; compounding?: string },
): { principal: number; interest: number; maturity_value: number } {
  const months = Math.trunc(opts.months);
  let interest: number;
  if (opts.compounding === 'monthly') {
    const monthly = opts.annual_rate / 12;
    let value = principal;
    for (let i = 0; i < Math.max(0, months); i++) value *= 1 + monthly;
    const raw = value - principal;
    interest = Math.sign(raw) * Math.round(Math.abs(raw)); // quantize half away from zero
  } else {
    // simple: principal * rate * months / 12, half-up to int paise (exact via integers).
    const { num, den } = rateFraction(opts.annual_rate);
    interest = roundHalfUpDiv(principal * num * months, den * 12);
  }
  return { principal, interest, maturity_value: principal + interest };
}

// ---- certificates / rights / buyback / dividend -------------------------------

export function shareCertificates(
  holders: { name: string; shares: number; form?: string }[],
  defaultForm = 'demat',
): Array<{
  certificate_no: string;
  name: string;
  shares: number;
  distinctive_from: number;
  distinctive_to: number;
  form: string;
}> {
  const certificates = [];
  let cursor = 1;
  let index = 0;
  for (const h of holders) {
    const shares = Math.trunc(h.shares);
    if (shares <= 0) continue;
    index += 1;
    certificates.push({
      certificate_no: `SC-${String(index).padStart(4, '0')}`,
      name: h.name,
      shares,
      distinctive_from: cursor,
      distinctive_to: cursor + shares - 1,
      form: h.form ?? defaultForm,
    });
    cursor += shares;
  }
  return certificates;
}

export function rightsEntitlement(
  holders: { name: string; shares: number }[],
  newShares: number,
): Array<{ name: string; shares: number; entitlement: number }> {
  const total = holders.reduce((s, h) => s + Math.trunc(h.shares), 0);
  return holders.map((h) => {
    const held = Math.trunc(h.shares);
    const entitlement = total > 0 ? Math.floor((held * newShares) / total) : 0;
    return { name: h.name, shares: held, entitlement };
  });
}

export function buybackCompliance(args: {
  paid_up_capital: number;
  free_reserves: number;
  buyback_amount: number;
  shares_bought_back?: number;
  total_shares?: number;
  post_buyback_debt?: number;
  post_buyback_equity?: number;
}): { permitted: boolean; max_amount: number; debt_equity_ratio: number; reasons: string[] } {
  const {
    paid_up_capital,
    free_reserves,
    buyback_amount,
    shares_bought_back = 0,
    total_shares = 0,
    post_buyback_debt = 0,
    post_buyback_equity = 0,
  } = args;
  const funds = paid_up_capital + free_reserves;
  const max_amount = Math.floor(funds / 4); // 25%
  const amount_ok = buyback_amount <= max_amount;
  const shares_ok = total_shares === 0 || shares_bought_back <= Math.floor(total_shares / 4);
  const ratio = post_buyback_equity ? post_buyback_debt / post_buyback_equity : 0.0;
  const ratio_ok = ratio <= 2.0;
  const reasons: string[] = [];
  if (!amount_ok) reasons.push('buyback exceeds 25% of paid-up capital + free reserves');
  if (!shares_ok) reasons.push('shares bought back exceed 25% of total equity');
  if (!ratio_ok) reasons.push('post-buyback debt:equity exceeds 2:1');
  return { permitted: amount_ok && shares_ok && ratio_ok, max_amount, debt_equity_ratio: round4(ratio), reasons };
}

export function dividendDistribution(args: {
  distributable_profit: number;
  declared: number;
  shares: number;
}): { permitted: boolean; declared: number; per_share: number; remaining_profit: number } {
  const { distributable_profit, declared, shares } = args;
  const permitted = declared >= 0 && declared <= distributable_profit;
  const payout = permitted ? declared : 0;
  const per_share = shares > 0 && permitted ? Math.floor(payout / shares) : 0;
  return { permitted, declared: payout, per_share, remaining_profit: distributable_profit - payout };
}
