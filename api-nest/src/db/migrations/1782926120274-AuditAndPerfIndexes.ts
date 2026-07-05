import { MigrationInterface, QueryRunner } from 'typeorm';

/**
 * Production-audit fixes (2026-07-05):
 *  - UNIQUE(prev_hash) on audit_log — a forked hash-chain link fails loud instead of silently corrupting.
 *  - UNIQUE(domain, captured_at, metric) on metric_snapshot — same-day re-capture upserts, never duplicates.
 *  - Indexes on foreign-key columns that were full-scanning on every hot lookup.
 */
export class AuditAndPerfIndexes1782926120274 implements MigrationInterface {
  name = 'AuditAndPerfIndexes1782926120274';

  public async up(q: QueryRunner): Promise<void> {
    await q.query(`CREATE UNIQUE INDEX "UQ_audit_log_prev_hash" ON "audit_log" ("prev_hash")`);
    await q.query(`CREATE UNIQUE INDEX "UQ_metric_snapshot_domain_day_metric" ON "metric_snapshot" ("domain", "captured_at", "metric")`);
    await q.query(`CREATE INDEX "IDX_journal_lines_entry" ON "journal_lines" ("journal_entry_id")`);
    await q.query(`CREATE INDEX "IDX_journal_lines_account" ON "journal_lines" ("account_id")`);
    await q.query(`CREATE INDEX "IDX_invoices_customer" ON "invoices" ("customer_id")`);
    await q.query(`CREATE INDEX "IDX_invoice_items_invoice" ON "invoice_items" ("invoice_id")`);
    await q.query(`CREATE INDEX "IDX_credit_notes_invoice" ON "credit_notes" ("invoice_id")`);
    await q.query(`CREATE INDEX "IDX_bank_transactions_account" ON "bank_transactions" ("account_id")`);
    await q.query(`CREATE INDEX "IDX_payroll_entries_run" ON "payroll_entries" ("payroll_run_id")`);
    await q.query(`CREATE INDEX "IDX_payroll_entries_employee" ON "payroll_entries" ("employee_id")`);
    await q.query(`CREATE INDEX "IDX_salary_structures_employee" ON "salary_structures" ("employee_id")`);
    await q.query(`CREATE INDEX "IDX_esop_grants_employee" ON "esop_grants" ("employee_id")`);
  }

  public async down(q: QueryRunner): Promise<void> {
    await q.query(`DROP INDEX "IDX_esop_grants_employee"`);
    await q.query(`DROP INDEX "IDX_salary_structures_employee"`);
    await q.query(`DROP INDEX "IDX_payroll_entries_employee"`);
    await q.query(`DROP INDEX "IDX_payroll_entries_run"`);
    await q.query(`DROP INDEX "IDX_bank_transactions_account"`);
    await q.query(`DROP INDEX "IDX_credit_notes_invoice"`);
    await q.query(`DROP INDEX "IDX_invoice_items_invoice"`);
    await q.query(`DROP INDEX "IDX_invoices_customer"`);
    await q.query(`DROP INDEX "IDX_journal_lines_account"`);
    await q.query(`DROP INDEX "IDX_journal_lines_entry"`);
    await q.query(`DROP INDEX "UQ_metric_snapshot_domain_day_metric"`);
    await q.query(`DROP INDEX "UQ_audit_log_prev_hash"`);
  }
}
