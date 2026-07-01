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
  if (url.startsWith('postgres')) {
    return {
      type: 'postgres',
      url,
      entities: ENTITIES,
      migrations: MIGRATIONS,
      // ponytail: schema is owned by migrations in prod; synchronize stays off.
      synchronize: false,
    };
  }
  // SQLite fallback (local dev / tests). Set MAISHA_DATABASE_FILE=':memory:' for tests.
  return {
    type: 'better-sqlite3',
    database: process.env.MAISHA_DATABASE_FILE ?? './data/maisha-nest.db',
    entities: ENTITIES,
    migrations: MIGRATIONS,
    synchronize: process.env.MAISHA_DB_SYNC !== 'false',
  };
}

// Used by the TypeORM CLI (migration generate/run). App uses buildDataSourceOptions via forRoot.
export default new DataSource(buildDataSourceOptions());
