/**
 * Budgeting & forecasting core — pure, deterministic. Faithful port of
 * api/app/domains/forecast/forecast_calc.py. Money is integer paise (JS number,
 * well under 2^53); ratios are floats.
 *
 * Where Python uses Decimal (scenario net change, unit-economics contribution/LTV),
 * we use BigInt integer arithmetic so there is zero float drift — `int(Decimal(...))`
 * truncates toward zero, which is exactly what BigInt division does.
 */

// ---- helpers ------------------------------------------------------------------

/** '2024-05' -> absolute month index (year*12 + month-1). */
function yearMonthIndex(yearMonth: string): number {
  const [year, month] = yearMonth.split('-');
  return parseInt(year, 10) * 12 + (parseInt(month, 10) - 1);
}

/** Round a float to 2 decimals, half away from zero (matches captured Python round(x, 2)). */
function round2(x: number): number {
  const s = Math.sign(x);
  return (s * Math.round(Math.abs(x) * 100)) / 100;
}

/**
 * Decompose a JS number's shortest decimal string into an exact bigint fraction num/den,
 * mirroring Python's Decimal(str(x)). ponytail: no scientific-notation support —
 * multipliers/margins are plain decimals; add expansion if that ever changes.
 */
function decFraction(x: number): [bigint, bigint] {
  const str = String(x);
  if (str.includes('e') || str.includes('E')) {
    throw new Error(`decFraction: scientific notation unsupported: ${str}`);
  }
  const neg = str.startsWith('-');
  const body = neg ? str.slice(1) : str;
  const [intp, frac = ''] = body.split('.');
  const num = BigInt((intp || '0') + frac) * (neg ? -1n : 1n);
  const den = 10n ** BigInt(frac.length);
  return [num, den];
}

// ---- revenue recognition ------------------------------------------------------

export interface RevContract {
  total_paise: number;
  start: string; // 'YYYY-MM'
  term_months: number;
}

export function revenueRecognitionForecast(
  contracts: RevContract[],
  opts: { horizon_months: number; start: string },
): { start: string; horizon_months: number; monthly: number[]; total_recognized: number } {
  const horizon = Math.trunc(opts.horizon_months);
  const startIdx = yearMonthIndex(opts.start);
  const monthly = new Array<number>(Math.max(0, horizon)).fill(0);
  for (const c of contracts) {
    const total = Math.trunc(c.total_paise);
    const term = Math.max(1, Math.trunc(c.term_months));
    const cStart = yearMonthIndex(c.start);
    // Python // on non-negative totals == BigInt trunc division.
    const perMonth = Number(BigInt(total) / BigInt(term));
    const remainder = total - perMonth * term; // trued up in the last month
    for (let k = 0; k < term; k++) {
      const idx = cStart + k - startIdx;
      if (idx >= 0 && idx < monthly.length) {
        monthly[idx] += perMonth + (k === term - 1 ? remainder : 0);
      }
    }
  }
  return {
    start: opts.start,
    horizon_months: horizon,
    monthly,
    total_recognized: monthly.reduce((s, v) => s + v, 0),
  };
}

// ---- variance -----------------------------------------------------------------

export function variance(
  actual: number,
  budget: number,
): { amount: number; pct: number; over_budget: boolean } {
  const amount = Math.trunc(actual) - Math.trunc(budget);
  const b = Math.trunc(budget);
  const pct = b ? round2((amount / b) * 100) : 0.0;
  return { amount, pct, over_budget: amount > 0 };
}

// ---- cash projection ----------------------------------------------------------

export function projectCash(
  openingCash: number,
  monthlyNetChange: number[],
): { balances: number[]; min_cash: number; months_to_zero: number | null } {
  const balances: number[] = [];
  let bal = Math.trunc(openingCash);
  let monthsToZero: number | null = null;
  monthlyNetChange.forEach((change, i) => {
    bal += Math.trunc(change);
    balances.push(bal);
    if (monthsToZero === null && bal < 0) monthsToZero = i;
  });
  const minCash = balances.length ? Math.min(...balances) : Math.trunc(openingCash);
  return { balances, min_cash: minCash, months_to_zero: monthsToZero };
}

// ---- scenarios ----------------------------------------------------------------

export function scenarioNetChange(
  baseRevenue: number,
  baseCost: number,
  opts: { revenue_mult?: number; extra_cost?: number } = {},
): number {
  const mult = opts.revenue_mult ?? 1.0;
  const extraCost = opts.extra_cost ?? 0;
  const [num, den] = decFraction(mult);
  // int(Decimal(base_revenue) * Decimal(str(mult))) — truncate toward zero.
  const revenue = Number((BigInt(Math.trunc(baseRevenue)) * num) / den);
  return revenue - (Math.trunc(baseCost) + Math.trunc(extraCost));
}

export function runwayMonths(cash: number, monthlyNetBurn: number): number | null {
  const burn = Math.trunc(monthlyNetBurn);
  if (burn <= 0) return null;
  return round2(Math.trunc(cash) / burn);
}

export function burnMultiple(netBurn: number, netNewArr: number): number | null {
  const arr = Math.trunc(netNewArr);
  if (arr <= 0) return null;
  return round2(Math.trunc(netBurn) / arr);
}

// ---- unit economics -----------------------------------------------------------

export function unitEconomics(args: {
  sales_marketing_spend: number;
  new_customers: number;
  arpu: number;
  gross_margin: number;
  lifetime_months: number;
}): { cac: number; ltv: number; payback_months: number | null; ltv_cac_ratio: number | null } {
  const { sales_marketing_spend, new_customers, arpu, gross_margin, lifetime_months } = args;
  if (new_customers <= 0) throw new Error('new_customers must be positive');
  const cac = Number(BigInt(Math.trunc(sales_marketing_spend)) / BigInt(Math.trunc(new_customers)));
  // contribution = Decimal(arpu) * Decimal(str(gross_margin)) — kept exact as arpu*gn/gd.
  const [gn, gd] = decFraction(gross_margin);
  const contribNum = BigInt(Math.trunc(arpu)) * gn; // over gd
  const ltv = Number((contribNum * BigInt(Math.trunc(lifetime_months))) / gd);
  const paybackMonths =
    contribNum > 0n ? round2(Number(BigInt(cac) * gd) / Number(contribNum)) : null;
  const ltvCac = cac > 0 ? round2(ltv / cac) : null;
  return { cac, ltv, payback_months: paybackMonths, ltv_cac_ratio: ltvCac };
}

// ---- rolling re-forecast ------------------------------------------------------

export function rollingReforecast(
  actuals: number[],
  budget: number[],
): {
  reforecast: number[];
  reforecast_total: number;
  original_total: number;
  variance: number;
  periods_actualised: number;
} {
  const elapsed = actuals.length;
  const reforecast = [...actuals.map((x) => Math.trunc(x)), ...budget.slice(elapsed).map((x) => Math.trunc(x))];
  const reforecastTotal = reforecast.reduce((s, v) => s + v, 0);
  const originalTotal = budget.reduce((s, v) => s + Math.trunc(v), 0);
  return {
    reforecast,
    reforecast_total: reforecastTotal,
    original_total: originalTotal,
    variance: reforecastTotal - originalTotal,
    periods_actualised: elapsed,
  };
}

// ---- headcount ----------------------------------------------------------------

export interface HeadcountRole {
  count: number;
  monthly_cost: number;
}

export function headcountForecast(
  roles: HeadcountRole[],
  opts: { months: number },
): { headcount: number; monthly_cost: number; annualised_cost: number; projection: number[] } {
  const headcount = roles.reduce((s, r) => s + Math.trunc(r.count), 0);
  const monthlyCost = roles.reduce((s, r) => s + Math.trunc(r.count) * Math.trunc(r.monthly_cost), 0);
  return {
    headcount,
    monthly_cost: monthlyCost,
    annualised_cost: monthlyCost * 12,
    projection: new Array<number>(Math.max(0, Math.trunc(opts.months))).fill(monthlyCost),
  };
}
