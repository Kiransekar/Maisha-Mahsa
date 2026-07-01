/**
 * Compliance service: the statutory calendar aggregating every deadline (GST 20th, TDS 7th,
 * PF/ESI 15th, PT, ROC) into one view, plus secretarial/audit/DPIIT helpers and the compliance
 * health snapshot for Mahsa. Deterministic — `asOf` injected. Mirrors
 * api/app/domains/compliance/service.py.
 */
import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { SnapshotProducer } from '../../core/loop.service';
import * as calc from './compliance.calc';
import { MarkFiledDto, NewDeadlineDto } from './compliance.dto';
import { ComplianceCalendar } from './compliance.entities';

// Standard monthly statutory deadlines: [domain, form_name, day-of-following-month].
const MONTHLY_DEADLINES: [string, string, number][] = [
  ['tds', 'TDS deposit', 7],
  ['pf', 'PF ECR', 15],
  ['esi', 'ESI contribution', 15],
  ['gst', 'GSTR-3B', 20],
  ['pt', 'Professional Tax', 21],
];

function nextMonth(month: string): [number, number] {
  const [year, m] = month.split('-').map((p) => parseInt(p, 10));
  return m === 12 ? [year + 1, 1] : [year, m + 1];
}

const pad = (n: number) => String(n).padStart(2, '0');

@Injectable()
export class ComplianceService implements SnapshotProducer {
  readonly domain = 'compliance';

  constructor(
    @InjectRepository(ComplianceCalendar)
    private readonly calendar: Repository<ComplianceCalendar>,
  ) {}

  // ---- calendar --------------------------------------------------------------

  async addDeadline(body: NewDeadlineDto): Promise<number> {
    const row = this.calendar.create({
      domain: body.domain,
      form_name: body.form_name,
      due_date: body.due_date,
      filing_period: body.filing_period ?? null,
    });
    await this.calendar.save(row);
    return row.id;
  }

  /** Seed the standard statutory deadlines for the liabilities of `month` (YYYY-MM), all
   * due in the following month. */
  async seedMonth(month: string): Promise<number[]> {
    const [ny, nm] = nextMonth(month);
    const ids: number[] = [];
    for (const [domain, form, day] of MONTHLY_DEADLINES) {
      const due = `${ny}-${pad(nm)}-${pad(day)}`;
      const id = await this.addDeadline({
        domain,
        form_name: `${form} (${month})`,
        due_date: due,
        filing_period: month,
      });
      ids.push(id);
    }
    return ids;
  }

  async markFiled(deadlineId: number, body: MarkFiledDto): Promise<void> {
    const row = await this.calendar.findOne({ where: { id: deadlineId } });
    if (row === null) throw new NotFoundException(`compliance deadline ${deadlineId} not found`);
    row.status = 'filed';
    row.filed_date = body.filed_date;
    row.acknowledgement = body.acknowledgement ?? null;
    await this.calendar.save(row);
  }

  private async entries(): Promise<calc.Entry[]> {
    const rows = await this.calendar.find();
    return rows.map((e) => ({
      domain: e.domain,
      form_name: e.form_name,
      due_date: e.due_date,
      status: e.status,
    }));
  }

  // ---- secretarial / audit-support / DPIIT (pure delegations) ----------------

  secretarialCalendar(fyEnd: string) {
    return calc.secretarialCalendar(fyEnd);
  }

  boardMeetingCompliance(meetingDates: string[]) {
    return calc.boardMeetingCompliance(meetingDates);
  }

  auditSupportPackage(available: Iterable<string>, auditType = 'statutory') {
    return calc.auditSupportPackage(available, auditType);
  }

  dpiitEligibility(args: {
    incorporationDate: string;
    asOf: string;
    annualTurnoverPaise: number;
    isReconstituted?: boolean;
  }) {
    return calc.dpiitEligibility(args);
  }

  async alerts(asOf: string): Promise<Record<string, any>[]> {
    return calc.alerts(await this.entries(), asOf);
  }

  // ---- Mahsa contract --------------------------------------------------------

  async buildSnapshot(asOf?: string): Promise<Record<string, any>> {
    const anchor = asOf ?? '1970-01-01';
    const entries = await this.entries();
    const overdue = calc.overdueCount(entries, anchor);
    const health = calc.domainHealth(entries, anchor);

    return {
      as_of: anchor,
      overdue_filings: overdue, // drives global COMPLIANCE-002
      metrics: {
        roc_filing_status: health.roc,
        gst_filing_status: health.gst,
        tds_filing_status: health.tds,
        pf_filing_status: health.pf,
        esi_filing_status: health.esi,
        pt_filing_status: health.pt,
        secretarial_score: 1.0,
        audit_readiness: 1.0,
      },
    };
  }
}
