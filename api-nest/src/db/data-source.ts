/**
 * TypeORM connection options, env-driven (12-factor). Postgres in prod, SQLite for
 * local/tests. Entities and migrations are discovered by glob so new domains need no wiring
 * here. Also exports a CLI DataSource for `typeorm migration:*`.
 */
import { join } from 'path';
import { DataSource, DataSourceOptions } from 'typeorm';

const ENTITIES = [join(__dirname, '..', '**', '*.entities.{ts,js}')];
const MIGRATIONS = [join(__dirname, 'migrations', '*.{ts,js}')];

export function buildDataSourceOptions(): DataSourceOptions {
  const url = process.env.MAISHA_DATABASE_URL ?? '';
  if (process.env.MAISHA_ENVIRONMENT === 'production' && !url.startsWith('postgres')) {
    // Never silently run production on an auto-synced SQLite schema — require Postgres + migrations.
    throw new Error('Production requires MAISHA_DATABASE_URL=postgres://…; refusing to run on SQLite.');
  }
  if (url.startsWith('postgres')) {
    return {
      type: 'postgres',
      url,
      entities: ENTITIES,
      migrations: MIGRATIONS,
      // ponytail: schema is owned by migrations in prod; synchronize stays off, migrations auto-run
      // so a missed deploy step can't silently boot the app against an empty schema.
      synchronize: false,
      migrationsRun: true,
    };
  }
  // SQLite fallback (local dev / tests). Set MAISHA_DATABASE_FILE=':memory:' for tests.
  return {
    type: 'better-sqlite3',
    database: process.env.MAISHA_DATABASE_FILE ?? './data/maisha-nest.db',
    entities: ENTITIES,
    migrations: MIGRATIONS,
    // Dev/test only (production is refused above unless on Postgres); sync builds the schema.
    synchronize: process.env.MAISHA_DB_SYNC !== 'false',
  };
}

// Used by the TypeORM CLI (migration generate/run). App uses buildDataSourceOptions via forRoot.
export default new DataSource(buildDataSourceOptions());
