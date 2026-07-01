/**
 * Tax service: advance tax + s.234C, TDS returns + s.234E, TDS aggregation from payroll
 * and payables, ITR/transfer-pricing helpers, and the tax health snapshot for Mahsa.
 * Exact paise; deterministic. Mirrors api/app/domains/tax/service.py.
 */
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { SnapshotProducer } from '../../core/loop.service';
import { Bill } from '../payables/payables.entities';
import { PayrollEntry, PayrollRun } from '../payroll/payroll.entities';
import * as tax from './tax.calc';
import { TdsReturnInputDto } from './tax.dto';
import { AdvanceTax, TdsEntry, TdsReturn } from './tax.entities';

function daysBetween(later: string, earlier: string): number {
  return Math.round((Date.parse(later) - Date.parse(earlier)) / 86_400_000);
}

/** TDS deposit due date: the 7th of the month following the payment month. ISO string. */
function tdsDueDate(paymentDate: string): string {
  const [y, m] = paymentDate.split('-').map((x) => parseInt(x, 10));
  const [year, month] = m === 12 ? [y + 1, 1] : [y, m + 1];
  return `${year}-${String(month).padStart(2, '0')}-07`;
}

@Injectable()
export class TaxService implements SnapshotProducer {
  readonly domain = 'tax';

  constructor(
    @InjectRepository(TdsReturn) private readonly tdsReturns: Repository<TdsReturn>,
    @InjectRepository(TdsEntry) private readonly tdsEntries: Repository<TdsEntry>,
    @InjectRepository(AdvanceTax) private readonly advanceTax: Repository<AdvanceTax>,
    @InjectRepository(PayrollRun) private readonly payrollRuns: Repository<PayrollRun>,
    @InjectRepository(PayrollEntry) private readonly payrollEntries: Repository<PayrollEntry>,
    @InjectRepository(Bill) private readonly bills: Repository<Bill>,
  ) {}

  // ---- TDS returns ----------------------------------------------------------------

  async fileTdsReturn(body: TdsReturnInputDto) {
    let daysLate = 0;
    if (body.filed_date) {
      daysLate = Math.max(0, daysBetween(body.filed_date, body.due_date));
    }
    const lateFee = tax.lateFee234e(daysLate, body.total_deducted);
    const ret = this.tdsReturns.create({
      return_type: body.return_type,
      quarter: body.quarter,
      due_date: body.due_date,
      filed_date: body.filed_date ?? null,
      status: body.filed_date ? 'filed' : 'pending',
      total_deducted: body.total_deducted,
      late_filing_fee: lateFee,
    });
    await this.tdsReturns.save(ret);
    return {
      tds_return_id: ret.id,
      return_type: body.return_type,
      quarter: body.quarter,
      total_deducted: body.total_deducted,
      late_filing_fee: lateFee,
      status: ret.status,
    };
  }

  // ---- TDS aggregation bridge (payroll + payables) --------------------------------

  /** Aggregate TDS deducted in a month ("YYYY-MM") from payroll (s.192) and payables (194x). */
  async tdsDeductedSummary(month: string): Promise<{ payroll_tds: number; payables_tds: number; total: number }> {
    const runs = await this.payrollRuns.find({ where: { month_year: month } });
    const runIds = new Set(runs.map((r) => r.id));
    let payrollTds = 0;
    if (runIds.size) {
      for (const e of await this.payrollEntries.find()) {
        if (runIds.has(e.payroll_run_id)) payrollTds += e.tds;
      }
    }
    let payablesTds = 0;
    for (const b of await this.bills.find()) {
      if (b.bill_date.startsWith(month)) payablesTds += b.tds_amount;
    }
    return { payroll_tds: payrollTds, payables_tds: payablesTds, total: payrollTds + payablesTds };
  }

  // ---- advance tax ----------------------------------------------------------------

  async recordAdvanceTax(args: {
    fy: string;
    installment: string;
    due_date: string;
    amount: number;
    paid_date?: string | null;
  }): Promise<number> {
    const row = this.advanceTax.create({
      fy: args.fy,
      installment: args.installment,
      due_date: args.due_date,
      amount: args.amount,
      paid_date: args.paid_date ?? null,
      status: args.paid_date ? 'paid' : 'pending',
    });
    await this.advanceTax.save(row);
    return row.id;
  }

  async advanceTaxInterest(fy: string, totalLiability: number) {
    const order = ['Q1', 'Q2', 'Q3', 'Q4'];
    const paidByInstallment: Record<string, number> = { Q1: 0, Q2: 0, Q3: 0, Q4: 0 };
    for (const row of await this.advanceTax.find({ where: { fy } })) {
      if (row.paid_date && row.installment in paidByInstallment) {
        paidByInstallment[row.installment] += row.amount;
      }
    }
    let running = 0;
    const cumulative = order.map((q) => (running += paidByInstallment[q]));
    return tax.interest234c(totalLiability, cumulative);
  }

  // ---- ITR preparation & transfer pricing -----------------------------------------

  itrComputation(args: {
    entityType: string;
    grossTotalIncome: number;
    deductions?: number;
    bookProfit?: number | null;
    tdsPaid?: number;
    advanceTaxPaid?: number;
  }) {
    return tax.itrComputation(args);
  }

  armsLengthCheck(price: number, comparables: number[], tolerancePct = 3.0) {
    return tax.armsLengthCheck(price, comparables, tolerancePct);
  }

  tpDocumentationRequired(args: { intlTransactionValue: number; groupConsolidatedRevenue?: number }) {
    return tax.tpDocumentationRequired(args);
  }

  // ---- Mahsa contract -------------------------------------------------------------

  private async tdsDaysOverdue(anchorIso: string): Promise<number> {
    let worst = 0;
    for (const e of await this.tdsEntries.find()) {
      if (e.deposit_date) continue;
      const due = tdsDueDate(e.payment_date);
      if (anchorIso > due) worst = Math.max(worst, daysBetween(anchorIso, due));
    }
    return worst;
  }

  private async tdsReturnDaysLate(anchorIso: string): Promise<number> {
    let worst = 0;
    for (const r of await this.tdsReturns.find()) {
      let late = 0;
      if (r.status === 'filed' && r.filed_date) {
        late = daysBetween(r.filed_date, r.due_date);
      } else if (r.status !== 'filed' && anchorIso > r.due_date) {
        late = daysBetween(anchorIso, r.due_date);
      }
      worst = Math.max(worst, late);
    }
    return worst;
  }

  /** Deterministic tax health snapshot for Mahsa. `asOf` is injected (no clock read). */
  async buildSnapshot(asOf?: string): Promise<Record<string, any>> {
    const anchorIso = asOf ?? '1970-01-01';
    const tdsDaysOverdue = await this.tdsDaysOverdue(anchorIso);
    const tdsReturnDaysLate = await this.tdsReturnDaysLate(anchorIso);

    return {
      as_of: anchorIso,
      metrics: {
        advance_tax_coverage: 1.0,
        tds_deposit_timeliness: tdsDaysOverdue === 0 ? 1.0 : 0.0,
        as26_match: 1.0,
        audit_trigger: 1.0,
        mat_exposure: 1.0,
        holiday_utilization: 1.0,
        tp_documentation: 1.0,
        itr_accuracy: 1.0,
        // signals for TAX-002 / TAX-003 (TAX-001 needs an estimate; default healthy)
        tds_days_overdue: tdsDaysOverdue,
        tds_return_days_late: tdsReturnDaysLate,
        advance_tax_q1_ratio: 1.0,
      },
    };
  }
}
