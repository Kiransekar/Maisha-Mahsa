import { MigrationInterface, QueryRunner } from 'typeorm';

/** Enterprise auth: per-user credentials, MFA, and active flag on the users table. */
export class EnterpriseAuth1782926120277 implements MigrationInterface {
  name = 'EnterpriseAuth1782926120277';

  public async up(q: QueryRunner): Promise<void> {
    await q.query(`ALTER TABLE "users" ADD COLUMN "password_hash" text`);
    await q.query(`ALTER TABLE "users" ADD COLUMN "mfa_secret" text`);
    await q.query(`ALTER TABLE "users" ADD COLUMN "mfa_enabled" integer NOT NULL DEFAULT 0`);
    await q.query(`ALTER TABLE "users" ADD COLUMN "active" integer NOT NULL DEFAULT 1`);
  }

  public async down(q: QueryRunner): Promise<void> {
    await q.query(`ALTER TABLE "users" DROP COLUMN "active"`);
    await q.query(`ALTER TABLE "users" DROP COLUMN "mfa_enabled"`);
    await q.query(`ALTER TABLE "users" DROP COLUMN "mfa_secret"`);
    await q.query(`ALTER TABLE "users" DROP COLUMN "password_hash"`);
  }
}
