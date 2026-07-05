import { MigrationInterface, QueryRunner } from 'typeorm';

/**
 * Memory Evolution (survey §5.2): non-destructive history for the hot layer + experiential feedback
 * so the optimizer learns which strategies this org adopts or dismisses.
 */
export class MemoryEvolution1782926120276 implements MigrationInterface {
  name = 'MemoryEvolution1782926120276';

  public async up(q: QueryRunner): Promise<void> {
    await q.query(
      `CREATE TABLE "org_memory_history" ("id" SERIAL NOT NULL, "company_id" integer NOT NULL DEFAULT 1, ` +
        `"kind" character varying NOT NULL, "content" text NOT NULL DEFAULT '', "superseded_at" character varying NOT NULL, ` +
        `CONSTRAINT "PK_org_memory_history" PRIMARY KEY ("id"))`,
    );
    await q.query(`CREATE INDEX "IDX_org_memory_history_company_kind" ON "org_memory_history" ("company_id", "kind")`);
    await q.query(
      `CREATE TABLE "playbook_feedback" ("id" SERIAL NOT NULL, "company_id" integer NOT NULL DEFAULT 1, ` +
        `"playbook_id" character varying NOT NULL, "decision" character varying NOT NULL, "at" character varying NOT NULL, ` +
        `CONSTRAINT "PK_playbook_feedback" PRIMARY KEY ("id"))`,
    );
    await q.query(`CREATE UNIQUE INDEX "UQ_playbook_feedback_company_playbook" ON "playbook_feedback" ("company_id", "playbook_id")`);
  }

  public async down(q: QueryRunner): Promise<void> {
    await q.query(`DROP INDEX "UQ_playbook_feedback_company_playbook"`);
    await q.query(`DROP TABLE "playbook_feedback"`);
    await q.query(`DROP INDEX "IDX_org_memory_history_company_kind"`);
    await q.query(`DROP TABLE "org_memory_history"`);
  }
}
