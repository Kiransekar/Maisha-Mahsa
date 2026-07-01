/**
 * Email HTML renderers. The Python side used Jinja templates in web/templates/email/; this
 * API-only port renders inline HTML from the composed context (no template-engine dependency —
 * ponytail: a few functions beat pulling in a renderer). `formatInr` gives the ₹ grouping the
 * Jinja `rupees` filter did.
 */
import { formatInr } from '../common/money';
import type { BriefPayload } from '../cfo/cfo';

function esc(s: unknown): string {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
}

const COLOR: Record<string, string> = { green: '#1a7f37', amber: '#9a6700', red: '#cf222e' };

export function renderDailyBrief(brief: BriefPayload, companyName: string): string {
  const rows = brief.scorecard
    .map(
      (h) =>
        `<tr><td>${esc(h.domain)}</td><td style="color:${COLOR[h.color] ?? '#000'}">${esc(h.status)}</td>` +
        `<td align="right">${h.score ?? '—'}</td><td>${h.requires_approval ? '⚠ approval' : ''}</td></tr>`,
    )
    .join('');
  const attention = brief.needs_attention.length
    ? `<p><b>${brief.needs_attention.length} domain(s) need attention:</b> ${brief.needs_attention.map((h) => esc(h.domain)).join(', ')}</p>`
    : '<p>All domains green. ✅</p>';
  return `<!doctype html><html><body style="font-family:system-ui,sans-serif">
<h2>${esc(companyName)} — Daily CFO Brief</h2>
<p>As of ${esc(brief.as_of)} · Overall score: <b>${brief.overall_score ?? '—'}</b></p>
${attention}
<table cellpadding="6" style="border-collapse:collapse" border="1">
<tr><th>Domain</th><th>Status</th><th>Score</th><th></th></tr>${rows}</table>
</body></html>`;
}

export function renderComplianceAlert(ctx: Record<string, any>): string {
  const li = (a: any, overdue: boolean) =>
    `<li>${esc(a.form_name ?? a.domain)} — due ${esc(a.due_date)}` +
    (overdue ? ` <b style="color:${COLOR.red}">(${a.days_overdue}d overdue)</b>` : ` (in ${a.days_to_due}d, ${esc(a.label)})`) +
    `</li>`;
  return `<!doctype html><html><body style="font-family:system-ui,sans-serif">
<h2>Compliance Alert</h2><p>As of ${esc(ctx.as_of)} · ${ctx.total} filing(s) need attention.</p>
${ctx.overdue.length ? `<h3 style="color:${COLOR.red}">Overdue</h3><ul>${ctx.overdue.map((a: any) => li(a, true)).join('')}</ul>` : ''}
${ctx.upcoming.length ? `<h3>Upcoming</h3><ul>${ctx.upcoming.map((a: any) => li(a, false)).join('')}</ul>` : ''}
</body></html>`;
}

export function renderPayrollApproval(ctx: Record<string, any>): string {
  const rows = (ctx.entries ?? [])
    .map((e: any) => `<tr><td>${esc(e.employee_name ?? e.employee_code)}</td><td align="right">${formatInr(e.gross_salary ?? e.gross ?? 0)}</td><td align="right">${formatInr(e.net_salary ?? e.net ?? 0)}</td></tr>`)
    .join('');
  return `<!doctype html><html><body style="font-family:system-ui,sans-serif">
<h2>Payroll Approval · ${esc(ctx.month_year)}</h2>
<p>Validation: <b>${esc(String(ctx.validation_status).toUpperCase())}</b>${ctx.mahsa_note ? ` — ${esc(ctx.mahsa_note)}` : ''}</p>
<p>${ctx.employee_count} employees · Gross <b>${formatInr(ctx.total_gross)}</b> · Deductions ${formatInr(ctx.total_deductions)} · Net <b>${formatInr(ctx.total_net)}</b></p>
<p>Employer PF ${formatInr(ctx.total_pf_employer)} · Employer ESI ${formatInr(ctx.total_esi_employer)}</p>
<table cellpadding="6" border="1" style="border-collapse:collapse"><tr><th>Employee</th><th>Gross</th><th>Net</th></tr>${rows}</table>
</body></html>`;
}

export function renderInvestorUpdate(ctx: Record<string, any>, companyName: string): string {
  const owners = Object.entries(ctx.cap_table?.ownership ?? {})
    .map(([who, pct]) => `<li>${esc(who)}: ${pct}%</li>`)
    .join('');
  const highlights = (ctx.highlights ?? []).map((h: string) => `<li>${esc(h)}</li>`).join('');
  return `<!doctype html><html><body style="font-family:system-ui,sans-serif">
<h2>${esc(companyName)} — Investor Update · ${esc(ctx.period)}</h2>
<p>Cash <b>${formatInr(ctx.cash)}</b> · Net burn ${formatInr(ctx.net_burn)} · Runway <b>${esc(ctx.runway_fmt)}</b> · AR ${formatInr(ctx.ar)}</p>
${highlights ? `<h3>Highlights</h3><ul>${highlights}</ul>` : ''}
<h3>Cap table (${ctx.cap_table?.total_shares ?? 0} shares)</h3><ul>${owners}</ul>
</body></html>`;
}

export function renderDunning(ctx: Record<string, any>, companyName: string): string {
  return `<!doctype html><html><body style="font-family:system-ui,sans-serif">
<h2>${esc(companyName)} — Payment reminder</h2>
<p>Dear ${esc(ctx.customer_name)},</p>
<p>${esc(ctx.message)}.</p>
<p>Invoice <b>${esc(ctx.invoice_number)}</b> · Outstanding <b>${formatInr(ctx.outstanding)}</b> · Due ${esc(ctx.due_date)}.</p>
<p>Thank you.</p></body></html>`;
}
