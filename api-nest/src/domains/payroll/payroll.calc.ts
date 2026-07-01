/**
 * Payroll statutory core — pure, exact (integer paise), deterministic.
 * Faithful port of api/app/domains/payroll/statutory.py + ecr.py and the pure
 * `compute_components` helper from service.py. No clock is read; the payroll month
 * (and `days_in_month`) are passed in. Re-verify rates/slabs against the current
 * Finance Act every year (FY 2025-26, new tax regime).
 *
 * Money is integer paise throughout. Every place Python uses Decimal we use integer
 * arithmetic (idiv / roundHalfUpDiv) so there is no float drift; Python
 * `ROUND_HALF_UP` = round half away from zero.
 */

import { paiseFromRupees } from '../../common/money';

// ---- integer/rounding helpers ---------------------------------------------------------

/** Truncate a/b toward zero, exact for integers (mirrors Python int(a/b) / Decimal int()). */
function idiv(a: number, b: number): number {
  return (a - (a % b)) / b;
}

/** Round paise to the nearest whole rupee, half away from zero (Python _round_rupee). */
function roundRupee(paise: number): number {
  const p = Math.trunc(paise);
  return Math.sign(p) * Math.round(Math.abs(p) / 100) * 100;
}

/** Round paise UP to the next whole rupee (ESI convention; Python -(-p//100)*100). */
function ceilRupee(paise: number): number {
  const p = Math.trunc(paise);
  return -Math.floor(-p / 100) * 100;
}

/** Round num/denom (denom>0) to an integer, half away from zero (ROUND_HALF_UP). */
function roundHalfUpDiv(num: number, denom: number): number {
  const sign = num < 0 ? -1 : 1;
  const a = Math.abs(num);
  return sign * idiv(2 * a + denom, 2 * denom);
}

// ---- statutory constants (FY 2025-26) -------------------------------------------------

const PF_WAGE_CEILING = paiseFromRupees(15000);
// PF 12%, EPS 8.33% — expressed as integer fractions to stay exact.
const PF_RATE_NUM = 12,
  PF_RATE_DEN = 100;
const EPS_RATE_NUM = 833,
  EPS_RATE_DEN = 10000;

const ESI_WAGE_CEILING = paiseFromRupees(21000);
const ESI_EMPLOYEE_NUM = 75,
  ESI_EMPLOYER_NUM = 325,
  ESI_RATE_DEN = 10000;

const BONUS_ELIGIBILITY_BASIC = paiseFromRupees(21000);
const BONUS_WAGE_CAP = paiseFromRupees(7000);
const BONUS_RATE_NUM = 833,
  BONUS_RATE_DEN = 10000; // 8.33%

const GRATUITY_NUM = 15,
  GRATUITY_DEN = 26;

const STD_DEDUCTION_ANNUAL = paiseFromRupees(75000);
const REBATE_LIMIT = paiseFromRupees(1200000); // s.87A: taxable <= 12L => nil tax
const CESS_NUM = 104,
  CESS_DEN = 100; // 1 + 4% cess

// New-regime annual slabs: [lowerPaise, upperPaise|null, pctNumerator] (rate over 100).
const TDS_SLABS: [number, number | null, number][] = [
  [paiseFromRupees(0), paiseFromRupees(400000), 0],
  [paiseFromRupees(400000), paiseFromRupees(800000), 5],
  [paiseFromRupees(800000), paiseFromRupees(1200000), 10],
  [paiseFromRupees(1200000), paiseFromRupees(1600000), 15],
  [paiseFromRupees(1600000), paiseFromRupees(2000000), 20],
  [paiseFromRupees(2000000), paiseFromRupees(2400000), 25],
  [paiseFromRupees(2400000), null, 30],
];

// Professional Tax monthly slabs by state: [grossUptoRupees|null, paise].
const PT_TABLES: Record<string, [number | null, number][]> = {
  MH: [[7500, 0], [10000, paiseFromRupees(175)], [null, paiseFromRupees(200)]],
  KA: [[24999, 0], [null, paiseFromRupees(200)]],
  WB: [
    [10000, 0], [15000, paiseFromRupees(110)], [25000, paiseFromRupees(130)],
    [40000, paiseFromRupees(150)], [null, paiseFromRupees(200)],
  ],
  GJ: [[12000, 0], [null, paiseFromRupees(200)]],
  AP: [[15000, 0], [20000, paiseFromRupees(150)], [null, paiseFromRupees(200)]],
  TS: [[15000, 0], [20000, paiseFromRupees(150)], [null, paiseFromRupees(200)]],
};

// LWF: [employeePaise, employerPaise, dueMonths]. Periodic remittance, not a payslip line.
const LWF_TABLES: Record<string, [number, number, number[]]> = {
  MH: [paiseFromRupees(25), paiseFromRupees(75), [6, 12]],
  KA: [paiseFromRupees(20), paiseFromRupees(40), [12]],
  TN: [paiseFromRupees(20), paiseFromRupees(40), [12]],
  GJ: [paiseFromRupees(6), paiseFromRupees(12), [6, 12]],
  WB: [paiseFromRupees(3), paiseFromRupees(15), [6, 12]],
  AP: [paiseFromRupees(30), paiseFromRupees(70), [12]],
  MP: [paiseFromRupees(10), paiseFromRupees(30), [6, 12]],
};

// ---- PF (EPF) -------------------------------------------------------------------------

/** PF wage = Basic capped at the ₹15,000 statutory ceiling. */
export function pfWage(basicMonthly: number): number {
  return Math.min(Math.trunc(basicMonthly), PF_WAGE_CEILING);
}

export function pfEmployee(basicMonthly: number): number {
  return roundRupee(idiv(pfWage(basicMonthly) * PF_RATE_NUM, PF_RATE_DEN));
}

export function pfEmployer(basicMonthly: number): number {
  return roundRupee(idiv(pfWage(basicMonthly) * PF_RATE_NUM, PF_RATE_DEN));
}

/** Employer EPS share = 8.33% of PF wage (max ₹1,250). */
export function epsEmployer(basicMonthly: number): number {
  return roundRupee(idiv(pfWage(basicMonthly) * EPS_RATE_NUM, EPS_RATE_DEN));
}

/** Employer EPF share = total employer 12% − EPS 8.33% (the 3.67% to EPF). */
export function epfEmployerDiff(basicMonthly: number): number {
  return pfEmployer(basicMonthly) - epsEmployer(basicMonthly);
}

// ---- ESI ------------------------------------------------------------------------------

/** [employee, employer] ESI. Nil when gross exceeds the ₹21,000 ceiling. */
export function esi(grossMonthly: number): [number, number] {
  const gross = Math.trunc(grossMonthly);
  if (gross > ESI_WAGE_CEILING) return [0, 0];
  const emp = ceilRupee(idiv(gross * ESI_EMPLOYEE_NUM, ESI_RATE_DEN));
  const empr = ceilRupee(idiv(gross * ESI_EMPLOYER_NUM, ESI_RATE_DEN));
  return [emp, empr];
}

// ---- Professional Tax -----------------------------------------------------------------

export function ptIsModelled(state: string | null | undefined): boolean {
  return (state ?? '').toUpperCase() in PT_TABLES;
}

/** Monthly PT for a modelled state; ₹0 otherwise. `month` is 1-12 (MH Feb ₹300 special). */
export function professionalTax(
  state: string | null | undefined,
  grossMonthly: number,
  month: number,
): number {
  const code = (state ?? '').toUpperCase();
  const table = PT_TABLES[code];
  if (!table) return 0;
  const grossRupees = idiv(Math.trunc(grossMonthly), 100);
  let amount = 0;
  for (const [upto, paise] of table) {
    if (upto === null || grossRupees <= upto) {
      amount = paise;
      break;
    }
  }
  if (code === 'MH' && month === 2 && amount === paiseFromRupees(200)) {
    amount = paiseFromRupees(300);
  }
  return amount;
}

// ---- Labour Welfare Fund --------------------------------------------------------------

export function lwfIsModelled(state: string | null | undefined): boolean {
  return (state ?? '').toUpperCase() in LWF_TABLES;
}

/** [employee, employer] LWF for `month` (1-12); non-zero only in the state's due month(s). */
export function labourWelfareFund(
  state: string | null | undefined,
  month: number,
): [number, number] {
  const entry = LWF_TABLES[(state ?? '').toUpperCase()];
  if (!entry) return [0, 0];
  const [employee, employer, dueMonths] = entry;
  return dueMonths.includes(Math.trunc(month)) ? [employee, employer] : [0, 0];
}

// ---- Leave & attendance (loss-of-pay) -------------------------------------------------

/** Loss-of-pay = monthly_amount × lop_days / days_in_month (capped at the month). */
export function lossOfPay(monthlyAmount: number, lopDays: number, daysInMonth = 30): number {
  if (Math.trunc(lopDays) <= 0) return 0;
  const days = Math.max(1, Math.trunc(daysInMonth));
  const lop = Math.min(Math.trunc(lopDays), days);
  return roundRupee(roundHalfUpDiv(Math.trunc(monthlyAmount) * lop, days));
}

/** Closing leave balance = opening + accrued − taken, floored at zero. */
export function leaveBalance(openingDays: number, accruedDays: number, takenDays: number): number {
  return Math.max(0.0, openingDays + accruedDays - takenDays);
}

// ---- TDS (Income-Tax s.192, new regime) -----------------------------------------------

function slabTax(taxableAnnual: number): number {
  const taxable = Math.trunc(taxableAnnual);
  let num = 0; // accumulate (top-lower)*pct, divide by 100 at the end (int() truncates)
  for (const [lower, upper, pct] of TDS_SLABS) {
    if (taxable <= lower) break;
    const top = upper === null ? taxable : Math.min(taxable, upper);
    if (top > lower) num += (top - lower) * pct;
  }
  return idiv(num, 100);
}

/** Annual income tax incl. 4% cess, after s.87A rebate and marginal relief (new regime). */
export function annualIncomeTax(annualTaxable: number): number {
  const taxable = Math.trunc(annualTaxable);
  if (taxable <= 0) return 0;
  let base = slabTax(taxable);
  if (taxable <= REBATE_LIMIT) {
    base = 0;
  } else {
    base = Math.min(base, taxable - REBATE_LIMIT); // marginal relief
  }
  const withCess = roundHalfUpDiv(base * CESS_NUM, CESS_DEN);
  return roundRupee(withCess);
}

/** Python round() — round half to even (banker's). Inputs here are >= 0. */
function pyRound(x: number): number {
  const floor = Math.floor(x);
  const frac = x - floor;
  if (frac < 0.5) return floor;
  if (frac > 0.5) return floor + 1;
  return floor % 2 === 0 ? floor : floor + 1; // exactly .5 → nearest even
}

/** Projected monthly TDS = annual tax on (annual gross − standard deduction) / 12. */
export function monthlyTds(annualGross: number): number {
  const taxable = Math.max(0, Math.trunc(annualGross) - STD_DEDUCTION_ANNUAL);
  const annual = annualIncomeTax(taxable);
  return roundRupee(pyRound(annual / 12));
}

// ---- Gratuity & Bonus provisions ------------------------------------------------------

/** Accrued gratuity liability = (15/26) × last drawn Basic × completed years. */
export function gratuityRequired(lastBasicMonthly: number, completedYears: number): number {
  if (completedYears <= 0) return 0;
  return roundRupee(
    roundHalfUpDiv(Math.trunc(lastBasicMonthly) * GRATUITY_NUM * completedYears, GRATUITY_DEN),
  );
}

/** Monthly statutory minimum bonus provision (8.33%). Nil if Basic > ₹21,000 ceiling. */
export function bonusProvisionMonthly(basicMonthly: number): number {
  const basic = Math.trunc(basicMonthly);
  if (basic > BONUS_ELIGIBILITY_BASIC) return 0;
  const cap = Math.min(basic, BONUS_WAGE_CAP);
  return roundRupee(idiv(cap * BONUS_RATE_NUM, BONUS_RATE_DEN));
}

// ---- salary composition ---------------------------------------------------------------

export type SalaryComponents = {
  gross_salary: number;
  basic: number;
  hra: number;
  lta: number;
  special_allowance: number;
  employee_pf: number;
  employer_pf: number;
  employee_esi: number;
  employer_esi: number;
  professional_tax: number;
  tds_monthly: number;
  loss_of_pay: number;
  lop_days: number;
  employee_deductions: number;
  net_salary: number;
  ctc: number;
};

/** Derive gross, statutory deductions, net pay and CTC for one month. Pure. */
export function computeComponents(args: {
  basic: number;
  hra: number;
  lta: number;
  special_allowance: number;
  state: string | null | undefined;
  month: number;
  lop_days?: number;
  days_in_month?: number;
}): SalaryComponents {
  const basic = Math.trunc(args.basic);
  const hra = Math.trunc(args.hra);
  const lta = Math.trunc(args.lta);
  const special = Math.trunc(args.special_allowance);
  const lopDays = Math.trunc(args.lop_days ?? 0);
  const daysInMonth = args.days_in_month ?? 30;

  const gross = basic + hra + lta + special;
  const empPf = pfEmployee(basic);
  const emprPf = pfEmployer(basic);
  const [empEsi, emprEsi] = esi(gross);
  const pt = professionalTax(args.state, gross, args.month);
  const tds = monthlyTds(gross * 12);
  const lop = lossOfPay(gross, lopDays, daysInMonth);
  const employeeDeductions = empPf + empEsi + pt + tds + lop;
  return {
    gross_salary: gross,
    basic,
    hra,
    lta,
    special_allowance: special,
    employee_pf: empPf,
    employer_pf: emprPf,
    employee_esi: empEsi,
    employer_esi: emprEsi,
    professional_tax: pt,
    tds_monthly: tds,
    loss_of_pay: lop,
    lop_days: lopDays,
    employee_deductions: employeeDeductions,
    net_salary: gross - employeeDeductions,
    ctc: gross + emprPf + emprEsi,
  };
}

// ---- EPFO ECR (Electronic Challan cum Return) text builder ----------------------------

const ECR_DELIMITER = '#~#';

export type EcrMember = {
  uan: string;
  member_name: string;
  gross_wages: number; // whole rupees
  epf_wages: number;
  eps_wages: number;
  edli_wages: number;
  epf_contri_remitted: number;
  eps_contri_remitted: number;
  epf_eps_diff_remitted: number;
  ncp_days?: number;
  refund_of_advances?: number;
};

const ECR_COLUMNS: (keyof EcrMember)[] = [
  'uan', 'member_name', 'gross_wages', 'epf_wages', 'eps_wages', 'edli_wages',
  'epf_contri_remitted', 'eps_contri_remitted', 'epf_eps_diff_remitted',
  'ncp_days', 'refund_of_advances',
];

export function ecrLine(m: EcrMember): string {
  return ECR_COLUMNS.map((c) => String(m[c] ?? 0)).join(ECR_DELIMITER);
}

/** The ECR text file body — one #~#-delimited line per member, newline-separated. */
export function buildEcr(members: EcrMember[]): string {
  return members.map(ecrLine).join('\n');
}
