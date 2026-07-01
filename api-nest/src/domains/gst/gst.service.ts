/**
 * GST service: GSTR-3B computation/persistence, GSTR-1 summary, ITC reconciliation.
 * Exact paise; deterministic. Mirrors api/app/domains/gst/service.py.
 * (The Mahsa fold loop / snapshot is deferred to a later migration slice.)
 */
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { SnapshotProducer } from '../../core/loop.service';
import * as gst from './gst.calc';
import { Gstr1InputDto, Gstr3bInputDto } from './gst.dto';
import { GstReturn, ItcRegister } from './gst.entities';

function daysBetween(later: string, earlier: string): number {
  const ms = Date.parse(later) - Date.parse(earlier);
  return Math.round(ms / 86_400_000);
}

@Injectable()
export class GstService implements SnapshotProducer {
  readonly domain = 'gst';

  constructor(
    @InjectRepository(GstReturn) private readonly returns: Repository<GstReturn>,
    @InjectRepository(ItcRegister) private readonly itc: Repository<ItcRegister>,
  ) {}

  async fileGstr3b(body: Gstr3bInputDto) {
    const daysLate = body.filed_date ? Math.max(0, daysBetween(body.filed_date, body.due_date)) : 0;
    const comp = gst.computeGstr3b(body.output, body.itc_available, {
      daysLate,
      isNil: body.is_nil,
    });
    const ret = this.returns.create({
      return_type: 'GSTR-3B',
      filing_period: body.filing_period,
      due_date: body.due_date,
      filed_date: body.filed_date ?? null,
      status: body.filed_date ? 'filed' : 'pending',
      tax_payable: comp.cash_total,
      tax_paid: body.filed_date ? comp.total_payable : 0,
      late_fee: comp.late_fee,
      interest: comp.interest,
    });
    await this.returns.save(ret);
    return {
      gst_return_id: ret.id,
      filing_period: body.filing_period,
      cash: comp.cash,
      cash_total: comp.cash_total,
      late_fee: comp.late_fee,
      interest: comp.interest,
      total_payable: comp.total_payable,
    };
  }

  buildGstr1(body: Gstr1InputDto) {
    return gst.buildGstr1(body.lines, body.filing_period);
  }

  async reconcileItc() {
    const rows = await this.itc.find();
    const available2b = rows
      .filter((r) => r.in_2b && r.eligible_itc)
      .reduce((s, r) => s + r.total_tax, 0);
    const claimed = rows.filter((r) => r.eligible_itc).reduce((s, r) => s + r.total_tax, 0);
    const ratio = available2b > 0 ? claimed / available2b : 1.0;
    return {
      available_2b_paise: available2b,
      claimed_paise: claimed,
      itc_claimed_ratio: Math.round(ratio * 1e6) / 1e6,
      gap_paise: Math.abs(claimed - available2b),
    };
  }

  /**
   * Deterministic GST health snapshot for Mahsa. Mirrors GstService.build_snapshot in
   * api/app/domains/gst/service.py. `asOf` is injected (no clock read).
   */
  async buildSnapshot(asOf?: string): Promise<Record<string, any>> {
    const anchorIso = asOf ?? '1970-01-01';

    const latest = await this.returns.findOne({
      where: { return_type: 'GSTR-3B' },
      order: { filing_period: 'DESC' },
    });

    let daysLate = 0;
    let filingTimeliness = 1.0;
    if (latest) {
      if (latest.status === 'filed' && latest.filed_date) {
        daysLate = Math.max(0, daysBetween(latest.filed_date, latest.due_date));
      } else if (latest.status !== 'filed' && anchorIso > latest.due_date) {
        daysLate = Math.max(0, daysBetween(anchorIso, latest.due_date));
      }
      filingTimeliness = daysLate > 0 ? 0.0 : 1.0;
    }

    const recon = await this.reconcileItc();
    const ratio = recon.itc_claimed_ratio;
    const gapFraction = Math.max(0.0, ratio - 1.0);
    const reconciliationGap = Math.max(0.0, 1.0 - gapFraction);

    return {
      as_of: anchorIso,
      metrics: {
        filing_timeliness: filingTimeliness,
        itc_optimization: 1.0,
        e_invoice_readiness: 1.0,
        hsn_accuracy: 1.0,
        rcm_compliance: 1.0,
        lut_validity: 1.0,
        reconciliation_gap: reconciliationGap,
        penalty_exposure: daysLate === 0 ? 1.0 : 0.0,
        gstr3b_days_late: daysLate,
        itc_claimed_ratio: ratio,
      },
    };
  }
}
