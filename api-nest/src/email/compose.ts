/**
 * Pure composers for the domain emails (PRD §6.2–6.4). Faithful port of api/app/core/email/compose.py.
 * Turn raw domain data into the JSON-able context each renderer uses. No DB/Mahsa/network.
 */

const DUNNING_TONE: Record<string, string> = {
  'T-7': 'a friendly heads-up — your invoice is due in a week',
  'T-3': 'a reminder — your invoice is due in 3 days',
  'T-1': 'your invoice is due tomorrow',
  'T+1': 'your invoice is now overdue',
  'T+7': 'your invoice is 7 days overdue — please arrange payment',
};

export function composeDunning(item: Record<string, any>, asOf: string): Record<string, any> {
  const stage = item.stage;
  return {
    as_of: asOf,
    invoice_number: item.invoice_number,
    customer_name: item.customer_name,
    outstanding: Math.trunc(item.outstanding),
    due_date: item.due_date,
    stage,
    message: DUNNING_TONE[stage] ?? 'your invoice payment is due',
    overdue: String(stage).startsWith('T+'),
  };
}

/** Payroll-run approval email context: totals + per-employee breakdown + Mahsa note. */
export function composePayrollApproval(
  run: Record<string, any>,
  entries: Record<string, any>[],
  validationStatus: string,
  mahsaNote = '',
): Record<string, any> {
  return {
    month_year: run.month_year,
    employee_count: run.employee_count,
    total_gross: run.total_gross,
    total_deductions: run.total_deductions,
    total_net: run.total_net,
    total_pf_employer: run.total_pf_employer,
    total_esi_employer: run.total_esi_employer,
    validation_status: validationStatus,
    mahsa_note: mahsaNote,
    entries,
  };
}

/** Quarterly investor update: headline KPIs + cap-table summary + highlights. */
export function composeInvestorUpdate(
  period: string,
  kpis: Record<string, any>,
  capTable: Record<string, any>,
  highlights: string[] = [],
): Record<string, any> {
  return {
    period,
    cash: kpis.cash ?? 0,
    net_burn: kpis.net_burn ?? 0,
    runway_fmt: kpis.runway_fmt ?? '—',
    ar: kpis.ar ?? 0,
    cap_table: { total_shares: capTable.total_shares ?? 0, ownership: capTable.pct ?? {} },
    highlights,
  };
}

/** Split compliance-calendar alerts into overdue vs upcoming for the alert email. */
export function composeComplianceAlert(alerts: Record<string, any>[], asOf: string): Record<string, any> {
  const overdue = alerts.filter((a) => a.label === 'OVERDUE');
  const upcoming = alerts.filter((a) => a.label !== 'OVERDUE');
  return {
    as_of: asOf,
    overdue: [...overdue].sort((a, b) => (b.days_overdue ?? 0) - (a.days_overdue ?? 0)),
    upcoming: [...upcoming].sort((a, b) => String(a.due_date).localeCompare(String(b.due_date))),
    total: alerts.length,
  };
}
