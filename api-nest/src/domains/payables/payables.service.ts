/**
 * Payables service: vendor bills with TDS + 3-way match, AP aging, MSME compliance, the
 * GST input-credit bridge, and the payables health snapshot. Exact paise; deterministic.
 * Mirrors api/app/domains/payables/service.py. (The LLM drafting step is a later slice.)
 */
import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { IsNull, Not, Repository } from 'typeorm';

import { SnapshotProducer } from '../../core/loop.service';
import * as calc from './payables.calc';
import { NewBillDto, NewVendorDto } from './payables.dto';
import { Bill, PurchaseOrder, Vendor } from './payables.entities';

/** Indian financial-year start (1 April) for an ISO date, as 'YYYY-MM-DD'. */
function fyStart(iso: string): string {
  const [y, m] = iso.split('-').map((x) => parseInt(x, 10));
  const year = m >= 4 ? y : y - 1;
  return `${year}-04-01`;
}

function addDays(iso: string, days: number): string {
  return new Date(Date.parse(iso) + days * 86_400_000).toISOString().slice(0, 10);
}

function daysBetween(later: string, earlier: string): number {
  return Math.round((Date.parse(later) - Date.parse(earlier)) / 86_400_000);
}

@Injectable()
export class PayablesService implements SnapshotProducer {
  readonly domain = 'payables';

  constructor(
    @InjectRepository(Vendor) private readonly vendors: Repository<Vendor>,
    @InjectRepository(PurchaseOrder) private readonly pos: Repository<PurchaseOrder>,
    @InjectRepository(Bill) private readonly bills: Repository<Bill>,
  ) {}

  // ---- vendors --------------------------------------------------------------------

  async createVendor(body: NewVendorDto): Promise<{ id: number }> {
    const vendor = this.vendors.create({
      name: body.name,
      gstin: body.gstin ?? null,
      pan: body.pan ?? null,
      msme_status: body.msme_status ? 1 : 0,
      payment_terms: body.payment_terms,
      tds_section: body.tds_section ?? null,
      payee_type: body.payee_type,
    });
    await this.vendors.save(vendor);
    return { id: vendor.id };
  }

  // ---- bills ----------------------------------------------------------------------

  private async aggregateYtd(vendorId: number, billDate: string): Promise<number> {
    const start = fyStart(billDate);
    const prior = await this.bills.find({ where: { vendor_id: vendorId } });
    return prior
      .filter((b) => start <= b.bill_date && b.bill_date < billDate)
      .reduce((s, b) => s + Math.trunc(b.subtotal), 0);
  }

  async createBill(body: NewBillDto): Promise<Record<string, any>> {
    const vendor = await this.vendors.findOne({ where: { id: body.vendor_id } });
    if (vendor === null) throw new NotFoundException(`vendor ${body.vendor_id} not found`);

    const igst = body.igst_amount ?? 0;
    const cgst = body.cgst_amount ?? 0;
    const sgst = body.sgst_amount ?? 0;
    const gstTotal = igst + cgst + sgst || (body.gst_amount ?? 0);

    let tdsPaise = 0;
    if (vendor.tds_section) {
      const tds = calc.tdsOnPayment(vendor.tds_section, body.subtotal, {
        payee_type: vendor.payee_type,
        category: body.tds_category ?? null,
        aggregate_ytd: await this.aggregateYtd(body.vendor_id, body.bill_date),
      });
      tdsPaise = tds.tds_paise;
    }

    let match: ReturnType<typeof calc.threeWayMatch> | null = null;
    if (body.po_id !== undefined && body.po_id !== null) {
      const po = await this.pos.findOne({ where: { id: body.po_id } });
      if (po !== null) {
        match = calc.threeWayMatch(po.total_amount, body.subtotal + gstTotal, {
          grn_amount: po.received_amount,
        });
      }
    }

    const totalPayable = body.subtotal + gstTotal - tdsPaise;
    const due = addDays(body.bill_date, vendor.payment_terms);

    const bill = this.bills.create({
      bill_number: body.bill_number,
      vendor_id: body.vendor_id,
      po_id: body.po_id ?? null,
      bill_date: body.bill_date,
      due_date: due,
      subtotal: body.subtotal,
      gst_amount: gstTotal,
      igst_amount: igst,
      cgst_amount: cgst,
      sgst_amount: sgst,
      tds_amount: tdsPaise,
      total_amount: totalPayable,
      itc_eligible: (body.itc_eligible ?? true) ? 1 : 0,
      status: 'open',
    });
    await this.bills.save(bill);
    return {
      bill_id: bill.id,
      bill_number: body.bill_number,
      subtotal: body.subtotal,
      tds_amount: tdsPaise,
      tds_section: vendor.tds_section,
      total_amount: totalPayable,
      due_date: due,
      three_way_match: match,
    };
  }

  async recordPayment(billId: number, amount: number, paidDate: string): Promise<void> {
    const bill = await this.bills.findOne({ where: { id: billId } });
    if (bill === null) throw new NotFoundException(`bill ${billId} not found`);
    bill.paid_amount = Math.trunc(bill.paid_amount) + Math.trunc(amount);
    if (bill.paid_amount >= bill.total_amount) {
      bill.status = 'paid';
      bill.paid_date = paidDate;
    }
    await this.bills.save(bill);
  }

  // ---- aging / MSME / concentration -----------------------------------------------

  private async openBills(): Promise<Bill[]> {
    const bills = await this.bills.find();
    return bills.filter((b) => Math.trunc(b.total_amount) - Math.trunc(b.paid_amount) > 0);
  }

  async apAging(asOf: string): Promise<Record<string, any>> {
    const open = await this.openBills();
    const payables = open.map((b) => ({
      due_date: b.due_date,
      outstanding_paise: Math.trunc(b.total_amount) - Math.trunc(b.paid_amount),
    }));
    return calc.apAging(payables, asOf);
  }

  async msmeMaxDaysUnpaid(asOf: string): Promise<number> {
    let worst = 0;
    for (const b of await this.openBills()) {
      const vendor = await this.vendors.findOne({ where: { id: b.vendor_id } });
      if (vendor && vendor.msme_status) {
        worst = Math.max(worst, daysBetween(asOf, b.bill_date));
      }
    }
    return worst;
  }

  async vendorConcentration(): Promise<number> {
    const byVendor = new Map<number, number>();
    for (const b of await this.openBills()) {
      const outstanding = Math.trunc(b.total_amount) - Math.trunc(b.paid_amount);
      byVendor.set(b.vendor_id, (byVendor.get(b.vendor_id) ?? 0) + outstanding);
    }
    const values = [...byVendor.values()];
    const total = values.reduce((s, v) => s + v, 0);
    if (total <= 0) return 0.0;
    const top = Math.max(...values, 0);
    return Math.round((top / total) * 1e6) / 1e6;
  }

  async maxMatchVariancePct(): Promise<number> {
    let worst = 0.0;
    const withPo = await this.bills.find({ where: { po_id: Not(IsNull()) } });
    for (const b of withPo) {
      const po = await this.pos.findOne({ where: { id: b.po_id! } });
      if (po === null) continue;
      const m = calc.threeWayMatch(po.total_amount, b.subtotal + b.gst_amount, {
        grn_amount: po.received_amount,
      });
      worst = Math.max(worst, m.max_variance_pct);
    }
    return worst;
  }

  // ---- recurring payables (SaaS auto-categorisation) ------------------------------

  async recurringPayables(): Promise<Record<string, any>[]> {
    const rows: calc.RecurringBill[] = [];
    for (const b of await this.bills.find()) {
      const vendor = await this.vendors.findOne({ where: { id: b.vendor_id } });
      rows.push({
        vendor_id: b.vendor_id,
        vendor_name: vendor ? vendor.name : '',
        bill_date: b.bill_date,
        amount_paise: Math.trunc(b.total_amount),
      });
    }
    return calc.detectRecurring(rows);
  }

  // ---- payment run (batch disbursement) -------------------------------------------

  async paymentRun(
    asOf: string,
    opts: { horizon_days?: number; execute?: boolean; paid_date?: string | null } = {},
  ): Promise<Record<string, any>> {
    const horizonDays = opts.horizon_days ?? 0;
    const execute = opts.execute ?? false;
    const cutoff = addDays(asOf, horizonDays);
    const lines: Record<string, any>[] = [];
    for (const b of await this.openBills()) {
      if (b.due_date > cutoff) continue;
      const vendor = await this.vendors.findOne({ where: { id: b.vendor_id } });
      lines.push({
        bill_id: b.id,
        bill_number: b.bill_number,
        vendor_id: b.vendor_id,
        vendor_name: vendor ? vendor.name : '',
        bank_account: vendor ? vendor.bank_account : null,
        ifsc: vendor ? vendor.ifsc : null,
        amount_paise: Math.trunc(b.total_amount) - Math.trunc(b.paid_amount),
        due_date: b.due_date,
        is_msme: vendor ? Boolean(vendor.msme_status) : false,
        days_to_due: daysBetween(b.due_date, asOf),
      });
    }
    // MSME first, then most overdue (smallest days_to_due) first.
    lines.sort((a, b) => {
      const am = a.is_msme ? 0 : 1;
      const bm = b.is_msme ? 0 : 1;
      return am !== bm ? am - bm : a.days_to_due - b.days_to_due;
    });
    const total = lines.reduce((s, line) => s + Math.trunc(line.amount_paise), 0);
    if (execute) {
      const payDate = opts.paid_date ?? asOf;
      for (const line of lines) {
        await this.recordPayment(line.bill_id, line.amount_paise, payDate);
      }
    }
    return {
      as_of: asOf,
      cutoff,
      count: lines.length,
      total_paise: total,
      lines,
      executed: execute,
    };
  }

  // ---- GST input-credit bridge ----------------------------------------------------

  async inputTaxCredit(filingPeriod: string): Promise<{ igst: number; cgst: number; sgst: number }> {
    const itc = { igst: 0, cgst: 0, sgst: 0 };
    for (const b of await this.bills.find()) {
      if (!b.itc_eligible || !b.bill_date.startsWith(filingPeriod)) continue;
      itc.igst += Math.trunc(b.igst_amount);
      itc.cgst += Math.trunc(b.cgst_amount);
      itc.sgst += Math.trunc(b.sgst_amount);
    }
    return itc;
  }

  // ---- Mahsa contract -------------------------------------------------------------

  async buildSnapshot(asOf?: string): Promise<Record<string, any>> {
    const anchor = asOf ?? '1970-01-01';
    const msmeDays = await this.msmeMaxDaysUnpaid(anchor);
    const maxVariance = await this.maxMatchVariancePct();
    const concentration = await this.vendorConcentration();
    const apTotal = (await this.apAging(anchor)).total_outstanding;

    return {
      as_of: anchor,
      ap_total: apTotal,
      metrics: {
        ap_turnover: 1.0,
        msme_compliance: msmeDays <= calc.MSME_PAYMENT_DAYS ? 1.0 : 0.0,
        tds_deposit_status: 1.0,
        po_coverage: 1.0,
        early_pay_discount_capture: 1.0,
        vendor_concentration: Math.max(0.0, 1.0 - concentration),
        recurring_spend: 1.0,
        dispute_rate: 1.0,
        // signals for PAYABLES-001 / PAYABLES-002
        msme_max_days_unpaid: msmeDays,
        max_match_variance_pct: maxVariance,
        vendor_concentration_ratio: concentration,
      },
    };
  }
}
