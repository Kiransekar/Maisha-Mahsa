/**
 * Expense service: claim submission with policy check, approval/reimbursement workflow,
 * receipt parsing, category analytics, card reconciliation, and the health snapshot for Mahsa.
 * Exact paise; deterministic. Mirrors api/app/domains/expense/service.py.
 *
 * Expense has no Mahsa sub-vector; Mahsa enforces EXPENSE-001 (no over-policy claims pending
 * approval) on the snapshot's `over_policy_claims`. `asOf` is injected (no clock read).
 */
import { Injectable, ServiceUnavailableException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { SnapshotProducer } from '../../core/loop.service';
import { imageToText, OcrUnavailable } from '../../ocr/ocr';
import * as expense from './expense.calc';
import { ExpenseClaim } from './expense.entities';

@Injectable()
export class ExpenseService implements SnapshotProducer {
  readonly domain = 'expense';

  constructor(
    @InjectRepository(ExpenseClaim) private readonly claims: Repository<ExpenseClaim>,
  ) {}

  // ---- claims ---------------------------------------------------------------------

  async submitClaim(args: {
    claim_date: string;
    expense_date: string;
    category: string;
    amount: number;
    gst_amount?: number;
    employee_id?: number | null;
    vendor_name?: string | null;
    description?: string | null;
  }) {
    const policy = expense.checkPolicy(args.category, args.amount);
    const claim = this.claims.create({
      employee_id: args.employee_id ?? null,
      claim_date: args.claim_date,
      expense_date: args.expense_date,
      category: args.category,
      amount: args.amount,
      gst_amount: args.gst_amount ?? 0,
      vendor_name: args.vendor_name ?? null,
      description: args.description ?? null,
      over_policy: policy.over_policy ? 1 : 0,
      status: 'submitted',
    });
    await this.claims.save(claim);
    return {
      claim_id: claim.id,
      amount: args.amount,
      over_policy: policy.over_policy,
      policy_limit: policy.limit,
      excess: policy.excess,
      petty_cash_eligible: expense.isPettyCashEligible(args.amount),
    };
  }

  async approveClaim(claimId: number, args: { approver: string; approved_date: string }) {
    const claim = await this.claims.findOne({ where: { id: claimId } });
    if (claim === null) throw new Error(`expense claim ${claimId} not found`);
    claim.status = 'approved';
    claim.approved_by = args.approver;
    claim.approved_date = args.approved_date;
    await this.claims.save(claim);
  }

  async markReimbursed(claimId: number, reimbursementDate: string) {
    const claim = await this.claims.findOne({ where: { id: claimId } });
    if (claim === null) throw new Error(`expense claim ${claimId} not found`);
    claim.status = 'reimbursed';
    claim.reimbursement_date = reimbursementDate;
    await this.claims.save(claim);
  }

  async categorySpend(): Promise<Record<string, number>> {
    const rows = await this.claims.find();
    return expense.categorySpend(
      rows.map((c) => ({ category: c.category, amount: Math.trunc(c.amount) })),
    );
  }

  parseReceipt(ocrText: string) {
    return expense.parseReceipt(ocrText);
  }

  /** OCR an uploaded receipt image, then run the deterministic parser on the recognized text.
   * Surfaces 503 when the tesseract binary isn't installed (OCR degrades cleanly). */
  async parseReceiptImage(imageBytes: Buffer) {
    try {
      const text = await imageToText(imageBytes);
      return { ocr_text: text, ...expense.parseReceipt(text) };
    } catch (e) {
      if (e instanceof OcrUnavailable) throw new ServiceUnavailableException(e.message);
      throw e;
    }
  }

  reconcileCard(
    statementLines: expense.StatementLine[],
    claims: expense.ClaimLine[],
    opts: { dateToleranceDays?: number; amountTolerancePaise?: number } = {},
  ) {
    return expense.reconcileCard(statementLines, claims, opts);
  }

  // ---- Mahsa contract -------------------------------------------------------------

  async buildSnapshot(asOf?: string): Promise<Record<string, any>> {
    const anchor = asOf ?? '1970-01-01';
    const rows = await this.claims.find();
    const openClaims = rows.filter((c) => c.status !== 'rejected');
    const overPolicy = openClaims.filter((c) => c.over_policy).length;
    const pending = openClaims
      .filter((c) => c.status === 'submitted' || c.status === 'approved')
      .reduce((s, c) => s + Math.trunc(c.amount), 0);
    return {
      as_of: anchor,
      metrics: {
        over_policy_claims: overPolicy,
        pending_reimbursement_paise: pending,
      },
    };
  }
}
