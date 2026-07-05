import { MigrationInterface, QueryRunner } from 'typeorm';

/** Semantic hot-layer memory (CFO Profile), one row per (company_id, kind). */
export class OrgMemory1782926120275 implements MigrationInterface {
  name = 'OrgMemory1782926120275';

  public async up(q: QueryRunner): Promise<void> {
    await q.query(
      `CREATE TABLE "org_memory" ("id" SERIAL NOT NULL, "company_id" integer NOT NULL DEFAULT 1, ` +
        `"kind" character varying NOT NULL, "content" text NOT NULL DEFAULT '', ` +
        `"updated_at" TIMESTAMP NOT NULL DEFAULT now(), CONSTRAINT "PK_org_memory" PRIMARY KEY ("id"))`,
    );
    await q.query(`CREATE UNIQUE INDEX "UQ_org_memory_company_kind" ON "org_memory" ("company_id", "kind")`);
  }

  public async down(q: QueryRunner): Promise<void> {
    await q.query(`DROP INDEX "UQ_org_memory_company_kind"`);
    await q.query(`DROP TABLE "org_memory"`);
  }
}
