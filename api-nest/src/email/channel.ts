/** The EmailChannel: compose + dispatch domain emails through a transport. Port of channel.py. */
import { BriefPayload } from '../cfo/cfo';
import {
  renderComplianceAlert,
  renderDailyBrief,
  renderDunning,
  renderInvestorUpdate,
  renderPayrollApproval,
} from './render';
import { Transport } from './transport';

export class EmailChannel {
  constructor(
    private readonly transport: Transport,
    private readonly sender = 'cfo@maisha-mahsa.local',
  ) {}

  private async send(to: string, subject: string, html: string): Promise<string> {
    await this.transport.send({ to, subject, html, sender: this.sender });
    return html;
  }

  async sendDailyBrief(to: string, brief: BriefPayload, companyName = 'Maisha-Mahsa'): Promise<string> {
    const html = renderDailyBrief(brief, companyName);
    const flagged = brief.needs_attention.length;
    const subject =
      `${companyName} — Daily CFO Brief (${brief.as_of})` +
      (flagged ? ` · ${flagged} need(s) attention` : ' · all green');
    return this.send(to, subject, html);
  }

  async sendComplianceAlert(to: string, ctx: Record<string, any>): Promise<string> {
    const html = renderComplianceAlert(ctx);
    return this.send(to, `Compliance Alert · ${ctx.total} filing(s) need attention`, html);
  }

  async sendDunning(to: string, ctx: Record<string, any>, companyName = 'Maisha-Mahsa'): Promise<string> {
    const html = renderDunning(ctx, companyName);
    return this.send(to, `Payment reminder · Invoice ${ctx.invoice_number} (${ctx.stage})`, html);
  }

  async sendPayrollApproval(to: string, ctx: Record<string, any>): Promise<string> {
    const html = renderPayrollApproval(ctx);
    return this.send(to, `Payroll Approval · ${ctx.month_year} · ${String(ctx.validation_status).toUpperCase()}`, html);
  }

  async sendInvestorUpdate(to: string, ctx: Record<string, any>, companyName = 'Maisha-Mahsa'): Promise<string> {
    const html = renderInvestorUpdate(ctx, companyName);
    return this.send(to, `${companyName} — Investor Update · ${ctx.period}`, html);
  }
}
