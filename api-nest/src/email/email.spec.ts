import { InMemoryTransport } from './transport';
import { EmailChannel } from './channel';
import { composeDunning, composeComplianceAlert, composePayrollApproval, composeInvestorUpdate } from './compose';

describe('email pipeline', () => {
  it('dunning: compose → render → transport captures with ₹ formatting', async () => {
    const t = new InMemoryTransport();
    const channel = new EmailChannel(t, 'cfo@acme.test');
    const ctx = composeDunning(
      { invoice_number: 'INV-1', customer_name: 'Acme', outstanding: 12345670, due_date: '2024-05-10', stage: 'T+7' },
      '2024-05-17',
    );
    await channel.sendDunning('buyer@acme.test', ctx, 'Acme Inc');

    expect(t.sent).toHaveLength(1);
    expect(t.sent[0].to).toBe('buyer@acme.test');
    expect(t.sent[0].subject).toContain('Invoice INV-1 (T+7)');
    expect(t.sent[0].html).toContain('₹1,23,456.70'); // formatInr(12345670)
    expect(ctx.overdue).toBe(true);
  });

  it('compliance alert: overdue sorted before upcoming, count in subject', async () => {
    const t = new InMemoryTransport();
    const channel = new EmailChannel(t);
    const ctx = composeComplianceAlert(
      [
        { form_name: 'GSTR-3B', due_date: '2024-05-20', label: 'T-7', days_to_due: 7 },
        { form_name: 'TDS', due_date: '2024-05-01', label: 'OVERDUE', days_overdue: 9 },
      ],
      '2024-05-13',
    );
    expect(ctx.overdue).toHaveLength(1);
    expect(ctx.total).toBe(2);
    await channel.sendComplianceAlert('cfo@acme.test', ctx);
    expect(t.sent[0].subject).toContain('2 filing(s)');
  });

  it('payroll approval + investor update render and dispatch', async () => {
    const t = new InMemoryTransport();
    const channel = new EmailChannel(t);
    const pa = composePayrollApproval(
      { month_year: '2024-05', employee_count: 2, total_gross: 14000000, total_deductions: 1800000, total_net: 12200000, total_pf_employer: 720000, total_esi_employer: 0 },
      [{ employee_name: 'Ravi', gross_salary: 7000000, net_salary: 6100000 }],
      'green',
    );
    await channel.sendPayrollApproval('cfo@acme.test', pa);
    expect(t.sent[0].subject).toBe('Payroll Approval · 2024-05 · GREEN');
    expect(t.sent[0].html).toContain('₹1,22,000.00'); // total_net formatted

    const iu = composeInvestorUpdate('Q1', { cash: 50000000, net_burn: 10000000, runway_fmt: '5.0 mo', ar: 3000000 }, { total_shares: 1000, pct: { Founders: 80 } }, ['Closed pilot']);
    await channel.sendInvestorUpdate('vc@fund.test', iu, 'Acme Inc');
    expect(t.sent[1].subject).toBe('Acme Inc — Investor Update · Q1');
    expect(t.sent[1].html).toContain('Founders: 80%');
  });
});
