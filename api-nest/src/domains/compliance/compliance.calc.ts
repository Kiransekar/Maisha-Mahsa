/**
 * Compliance-calendar logic — pure, deterministic. Faithful port of
 * api/app/domains/compliance/compliance_calc.py. Time is injected via `asOf`
 * (ISO date string, YYYY-MM-DD). No clock read here.
 *
 * Dates are ISO strings throughout. Day arithmetic uses UTC epoch days to avoid
 * DST drift; ISO date lexicographic order == chronological order for `<` compares.
 */

export const STATUTORY_DOMAINS = ['roc', 'gst', 'tds', 'pf', 'esi', 'pt'] as const;

// ---- date helpers (UTC, no clock) --------------------------------------------

function utcMs(iso: string): number {
  const [y, m, d] = iso.split('-').map((x) => parseInt(x, 10));
  return Date.UTC(y, m - 1, d);
}

/** Whole-day count from `earlier` to `later` (later - earlier), like Python timedelta.days. */
function daysBetween(later: string, earlier: string): number {
  return Math.round((utcMs(later) - utcMs(earlier)) / 86_400_000);
}

function fmt(ms: number): string {
  const d = new Date(ms);
  const y = d.getUTCFullYear();
  const mo = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  return `${y}-${mo}-${day}`;
}

function addDays(iso: string, days: number): string {
  return fmt(utcMs(iso) + days * 86_400_000);
}

// Python floor division / modulo (JS % follows sign of dividend).
function floorDiv(a: number, b: number): number {
  return Math.floor(a / b);
}
function floorMod(a: number, b: number): number {
  return ((a % b) + b) % b;
}
function daysInMonth(year: number, month1: number): number {
  return new Date(Date.UTC(year, month1, 0)).getUTCDate();
}

/** Mirror of _add_months: shift an ISO date by `months`, clamping the day to month length. */
export function addMonths(iso: string, months: number): string {
  const [y, m, d] = iso.split('-').map((x) => parseInt(x, 10));
  const total = m - 1 + months;
  const year = y + floorDiv(total, 12);
  const month = floorMod(total, 12) + 1;
  const day = Math.min(d, daysInMonth(year, month));
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function round(x: number, ndigits: number): number {
  const f = 10 ** ndigits;
  return Math.round(x * f) / f;
}

// ---- MCA annual filings ------------------------------------------------------

export function mcaDeadlines(agmDate: string): Record<string, string>[] {
  const year = agmDate.slice(0, 4);
  return [
    { domain: 'roc', form: 'AOC-4', statute: 'Companies Act 2013 s.137', due_date: addDays(agmDate, 30) },
    { domain: 'roc', form: 'MGT-7', statute: 'Companies Act 2013 s.92', due_date: addDays(agmDate, 60) },
    { domain: 'roc', form: 'DPT-3', statute: 'Companies Act 2013 Rule 16', due_date: `${year}-06-30` },
    { domain: 'roc', form: 'DIR-3 KYC', statute: 'Companies Act 2013 Rule 12A', due_date: `${year}-09-30` },
  ];
}

// ---- Secretarial compliance --------------------------------------------------

export function boardMeetingCompliance(meetingDates: string[]): Record<string, any> {
  const dates = [...meetingDates].sort();
  const countOk = dates.length >= 4;
  const gaps: number[] = [];
  for (let i = 1; i < dates.length; i++) gaps.push(daysBetween(dates[i], dates[i - 1]));
  const maxGap = gaps.length ? Math.max(...gaps) : 0;
  const gapOk = maxGap <= 120;
  const reasons: string[] = [];
  if (!countOk) reasons.push('fewer than 4 board meetings in the year');
  if (dates.length > 1 && !gapOk)
    reasons.push(`gap of ${maxGap} days exceeds 120 between consecutive meetings`);
  return { compliant: countOk && gapOk, meetings: dates.length, max_gap_days: maxGap, reasons };
}

export function secretarialCalendar(fyEnd: string): Record<string, string>[] {
  const fyStart = addMonths(fyEnd, -12);
  const items: Record<string, string>[] = [
    { item: 'Annual General Meeting', statute: 'Companies Act 2013 s.96', due_date: addMonths(fyEnd, 6) },
    { item: 'Maintain statutory registers', statute: 'Companies Act 2013 s.88', due_date: fyEnd },
    { item: 'Record minutes of meetings', statute: 'Companies Act 2013 s.118', due_date: fyEnd },
  ];
  for (let q = 0; q < 4; q++) {
    items.push({
      item: `Board meeting Q${q + 1}`,
      statute: 'Companies Act 2013 s.173',
      due_date: addMonths(fyStart, q * 3 + 3),
    });
  }
  return items;
}

// ---- Audit support package ---------------------------------------------------

export const AUDIT_CHECKLIST = [
  'trial_balance', 'general_ledger', 'bank_statements', 'bank_reconciliation',
  'fixed_asset_register', 'gst_returns', 'tds_returns', 'payroll_records',
  'invoices', 'bills', 'board_minutes', 'cap_table',
] as const;

export function auditSupportPackage(
  available: Iterable<string>,
  auditType = 'statutory',
): Record<string, any> {
  const have = new Set(available);
  const missing = AUDIT_CHECKLIST.filter((i) => !have.has(i));
  const present = AUDIT_CHECKLIST.length - missing.length;
  return {
    audit_type: auditType,
    items: AUDIT_CHECKLIST.map((i) => ({ item: i, present: have.has(i) })),
    missing,
    readiness_pct: round((100.0 * present) / AUDIT_CHECKLIST.length, 1),
  };
}

// ---- DPIIT Startup India recognition -----------------------------------------

const DPIIT_MAX_TURNOVER_PAISE = 100 * 10 ** 7 * 100; // Rs 100 crore, in paise

export function dpiitEligibility(args: {
  incorporationDate: string;
  asOf: string;
  annualTurnoverPaise: number;
  isReconstituted?: boolean;
}): Record<string, any> {
  const isReconstituted = args.isReconstituted ?? false;
  const ageYears = daysBetween(args.asOf, args.incorporationDate) / 365.25;
  const ageOk = ageYears < 10;
  const turnoverOk = Math.trunc(args.annualTurnoverPaise) < DPIIT_MAX_TURNOVER_PAISE;
  const reasons: string[] = [];
  if (!ageOk) reasons.push('incorporated 10 or more years ago');
  if (!turnoverOk) reasons.push('annual turnover is Rs.100 crore or more');
  if (isReconstituted) reasons.push('formed by splitting up / reconstructing an existing business');
  return {
    eligible: ageOk && turnoverOk && !isReconstituted,
    age_years: round(ageYears, 2),
    reasons,
  };
}

// ---- Calendar alerts / health ------------------------------------------------

export type Entry = { domain?: string; form_name?: string; due_date: string; status?: string };

// Reminder cadence (PRD §1.10): T-7, T-1, T-0.
const ALERT_OFFSETS: Record<number, string> = { 7: 'T-7', 1: 'T-1', 0: 'T-0' };

function pending(entries: Entry[]): Entry[] {
  return entries.filter((e) => e.status !== 'filed');
}

export function overdueCount(entries: Entry[], asOf: string): number {
  return pending(entries).filter((e) => e.due_date < asOf).length;
}

export function domainHealth(entries: Entry[], asOf: string): Record<string, number> {
  const health: Record<string, number> = {};
  for (const d of STATUTORY_DOMAINS) health[d] = 1.0;
  for (const e of pending(entries)) {
    if (e.domain && e.domain in health && e.due_date < asOf) health[e.domain] = 0.0;
  }
  return health;
}

function label(e: Entry): Record<string, any> {
  return { domain: e.domain, form_name: e.form_name, due_date: e.due_date };
}

export function alerts(entries: Entry[], asOf: string): Record<string, any>[] {
  const out: Record<string, any>[] = [];
  for (const e of pending(entries)) {
    const delta = daysBetween(e.due_date, asOf);
    if (delta < 0) {
      out.push({ ...label(e), label: 'OVERDUE', days_overdue: -delta });
    } else if (delta in ALERT_OFFSETS) {
      out.push({ ...label(e), label: ALERT_OFFSETS[delta], days_to_due: delta });
    }
  }
  return out;
}
