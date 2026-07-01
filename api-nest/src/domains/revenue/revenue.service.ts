/**
 * Revenue service: invoicing, AR aging, dunning, customer concentration, and the
 * revenue health snapshot for Mahsa. Exact paise; deterministic (`asOf` injected).
 * Mirrors api/app/domains/revenue/service.py.
 */
import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Not, Repository } from 'typeorm';

import { Company } from '../../common/shared.entities';
import { SnapshotProducer } from '../../core/loop.service';
import * as revenue from './revenue.calc';
import { NewCustomerDto, NewInvoiceDto } from './revenue.dto';
import { Customer, Invoice, InvoiceItem } from './revenue.entities';

/** ISO date + N days, as an ISO date string (UTC, no clock read). */
function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

@Injectable()
export class RevenueService implements SnapshotProducer {
  readonly domain = 'revenue';

  constructor(
    @InjectRepository(Customer) private readonly customers: Repository<Customer>,
    @InjectRepository(Invoice) private readonly invoices: Repository<Invoice>,
    @InjectRepository(InvoiceItem) private readonly items: Repository<InvoiceItem>,
    @InjectRepository(Company) private readonly companies: Repository<Company>,
  ) {}

  // ---- customers ------------------------------------------------------------------

  async createCustomer(body: NewCustomerDto): Promise<{ id: number }> {
    const cust = this.customers.create({
      name: body.name,
      gstin: body.gstin ?? null,
      pan: body.pan ?? null,
      state: body.state ?? null,
      payment_terms: body.payment_terms ?? 30,
      tds_applicable: body.tds_applicable ? 1 : 0,
      tds_rate: body.tds_rate ?? 0.0,
    });
    await this.customers.save(cust);
    return { id: cust.id };
  }

  // ---- invoicing ------------------------------------------------------------------

  private async supplierState(): Promise<string | null> {
    const company = await this.companies.find({ take: 1 });
    return company.length ? company[0].state : null;
  }

  async createInvoice(body: NewInvoiceDto): Promise<Record<string, any>> {
    const customer = await this.customers.findOne({ where: { id: body.customer_id } });
    if (customer === null) throw new NotFoundException(`customer ${body.customer_id} not found`);

    const supplierState = await this.supplierState();
    // Inter-state when both states are known and differ; default intra-state otherwise.
    const interState = Boolean(supplierState && customer.state && supplierState !== customer.state);
    const lines = body.lines.map((ln) => ({ ...ln }));
    const comp = revenue.computeInvoice(lines, {
      gstRate: body.gst_rate,
      interState,
      tdsRate: customer.tds_applicable ? customer.tds_rate : 0,
    });

    const due = addDays(body.invoice_date, customer.payment_terms);
    const invoice = this.invoices.create({
      invoice_number: body.invoice_number,
      customer_id: body.customer_id,
      invoice_date: body.invoice_date,
      due_date: due,
      subtotal: comp.subtotal,
      gst_rate: body.gst_rate,
      igst_amount: comp.igst_amount,
      cgst_amount: comp.cgst_amount,
      sgst_amount: comp.sgst_amount,
      total_amount: comp.total_amount,
      tds_amount: comp.tds_amount,
      net_receivable: comp.net_receivable,
      irn: body.irn ?? null,
      status: 'issued',
    });
    await this.invoices.save(invoice);
    for (const ln of body.lines) {
      const qty = Math.trunc(Number(ln.quantity ?? 1));
      const rate = Math.trunc(Number(ln.rate));
      await this.items.save(
        this.items.create({
          invoice_id: invoice.id,
          description: ln.description ?? '',
          hsn_code: ln.hsn_code ?? null,
          quantity: qty,
          rate,
          amount: qty * rate,
        }),
      );
    }
    return {
      invoice_id: invoice.id,
      invoice_number: body.invoice_number,
      due_date: due,
      ...comp,
    };
  }

  async recordPayment(invoiceId: number, amount: number, paidDate: string): Promise<void> {
    const invoice = await this.invoices.findOne({ where: { id: invoiceId } });
    if (invoice === null) throw new NotFoundException(`invoice ${invoiceId} not found`);
    invoice.paid_amount = Math.trunc(invoice.paid_amount) + Math.trunc(amount);
    if (invoice.paid_amount >= invoice.net_receivable) {
      invoice.status = 'paid';
      invoice.paid_date = paidDate;
    }
    await this.invoices.save(invoice);
  }

  // ---- AR aging / dunning ---------------------------------------------------------

  private async openReceivables(): Promise<Invoice[]> {
    const rows = await this.invoices.find({ where: { status: Not('draft') } });
    return rows.filter((i) => i.net_receivable - i.paid_amount > 0);
  }

  async arAging(asOf: string): Promise<Record<string, any>> {
    const open = await this.openReceivables();
    const receivables = open.map((i) => ({
      due_date: i.due_date,
      outstanding_paise: i.net_receivable - i.paid_amount,
    }));
    return revenue.arAging(receivables, asOf);
  }

  async dueDunning(asOf: string): Promise<{ invoice_number: string; reminder: string }[]> {
    const out: { invoice_number: string; reminder: string }[] = [];
    for (const i of await this.openReceivables()) {
      for (const label of revenue.dunningDue(i.due_date, asOf)) {
        out.push({ invoice_number: i.invoice_number, reminder: label });
      }
    }
    return out;
  }

  /** Full dunning context per outstanding invoice with a reminder due as of `asOf` — feeds the
   * dunning email composer. Mirrors the Python RevenueService.pending_dunning. */
  async pendingDunning(asOf: string): Promise<Record<string, any>[]> {
    const out: Record<string, any>[] = [];
    for (const i of await this.openReceivables()) {
      const stages = revenue.dunningDue(i.due_date, asOf);
      if (stages.length === 0) continue;
      const customer = await this.customers.findOne({ where: { id: i.customer_id } });
      out.push({
        invoice_number: i.invoice_number,
        customer_name: customer?.name ?? '',
        customer_email: customer?.email ?? '',
        outstanding: i.net_receivable - i.paid_amount,
        due_date: i.due_date,
        stage: stages[0],
      });
    }
    return out;
  }

  async customerConcentration(): Promise<{ total_outstanding: number; largest: number; ratio: number }> {
    const byCustomer = new Map<number, number>();
    for (const i of await this.openReceivables()) {
      const outstanding = i.net_receivable - i.paid_amount;
      byCustomer.set(i.customer_id, (byCustomer.get(i.customer_id) ?? 0) + outstanding);
    }
    const values = [...byCustomer.values()];
    const total = values.reduce((s, v) => s + v, 0);
    const largest = values.length ? Math.max(...values) : 0;
    const ratio = total > 0 ? largest / total : 0.0;
    return { total_outstanding: total, largest, ratio: Math.round(ratio * 1e6) / 1e6 };
  }

  // ---- Mahsa contract -------------------------------------------------------------

  async buildSnapshot(asOf?: string): Promise<Record<string, any>> {
    const anchor = asOf ?? '1970-01-01';
    const aging = await this.arAging(anchor);
    const totalAr = aging.total_outstanding;
    const overdue90 = aging.buckets['90+'];
    const creditRisk = totalAr > 0 ? 1.0 - overdue90 / totalAr : 1.0;

    const concentration = await this.customerConcentration();
    const concRatio = concentration.ratio;

    // Trailing-12-month turnover and IRN coverage across issued invoices.
    const cutoff = addDays(anchor, -365);
    const all = await this.invoices.find({ where: { status: Not('draft') } });
    const issued = all.filter((i) => cutoff < i.invoice_date && i.invoice_date <= anchor);
    const annualTurnoverPaise = issued.reduce((s, i) => s + i.total_amount, 0);
    const missingIrn = issued.filter((i) => !i.irn).length;
    const irnCoverage = issued.length ? (issued.length - missingIrn) / issued.length : 1.0;

    return {
      as_of: anchor,
      monthly_revenue: Math.trunc(issued.reduce((s, i) => s + i.total_amount, 0) / 12),
      metrics: {
        ar_turnover: 1.0,
        dunning_effectiveness: 1.0,
        credit_risk: Math.max(0.0, creditRisk),
        revenue_quality: 1.0,
        deferred_revenue: 1.0,
        export_ratio: 1.0,
        irn_coverage: irnCoverage,
        customer_concentration: Math.max(0.0, 1.0 - concRatio),
        // signals for REVENUE-001 / REVENUE-002
        annual_turnover_rupees: Math.trunc(annualTurnoverPaise / 100),
        einvoice_missing: missingIrn,
        customer_concentration_ratio: concRatio,
      },
    };
  }
}
