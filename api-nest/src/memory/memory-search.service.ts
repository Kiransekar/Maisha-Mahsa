/**
 * Episodic recall over the hash-chained audit log — the "Evidence Layer" from the Hermes memory
 * schema, adapted. Lexical, not semantic (BM25 on SQLite FTS5 / ts_rank on Postgres): dramatically
 * cheaper, zero extra infra, and honest — a precise question gets precise decisions back.
 *
 * Maisha's episodic unit is a single *sealed decision* (one audit row), not a 200-message session,
 * so the article's "session bookends" collapse to "return the matched decisions, ranked".
 *
 * Golden Rule: recall surfaces what *happened* (action, domain, verdict, when) — never a number as
 * current truth. The index maintains itself via triggers (SQLite) or a functional index (Postgres),
 * so it can never drift from the source. Best-effort: any setup failure degrades to LIKE, never a
 * failed boot.
 */
import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { InjectDataSource } from '@nestjs/typeorm';
import { DataSource } from 'typeorm';

export interface RecallHit {
  id: number;
  timestamp: string;
  action: string;
  domain: string;
  validation_status: string | null;
  query: string | null;
  this_hash: string;
}

const CONTENT = `coalesce(action,'')||' '||coalesce(domain,'')||' '||coalesce(query,'')||' '||coalesce(validation_status,'')`;
const NEW_CONTENT = `coalesce(new.action,'')||' '||coalesce(new.domain,'')||' '||coalesce(new.query,'')||' '||coalesce(new.validation_status,'')`;

@Injectable()
export class MemorySearchService implements OnModuleInit {
  private readonly log = new Logger('memory.recall');
  private mode: 'fts5' | 'tsvector' | 'like' = 'like';

  constructor(@InjectDataSource() private readonly ds: DataSource) {}

  async onModuleInit(): Promise<void> {
    try {
      if (this.ds.options.type === 'better-sqlite3') await this.setupSqlite();
      else if (this.ds.options.type === 'postgres') await this.setupPostgres();
    } catch (e) {
      this.log.warn(`full-text index unavailable, falling back to LIKE: ${(e as Error).message}`);
      this.mode = 'like';
    }
  }

  private async setupSqlite(): Promise<void> {
    await this.ds.query(`CREATE VIRTUAL TABLE IF NOT EXISTS audit_fts USING fts5(content)`);
    // Self-maintaining: append-only source, so insert + delete triggers are enough (no update).
    await this.ds.query(
      `CREATE TRIGGER IF NOT EXISTS audit_fts_ai AFTER INSERT ON audit_log BEGIN
         INSERT INTO audit_fts(rowid, content) VALUES (new.id, ${NEW_CONTENT});
       END`,
    );
    await this.ds.query(
      `CREATE TRIGGER IF NOT EXISTS audit_fts_ad AFTER DELETE ON audit_log BEGIN
         INSERT INTO audit_fts(audit_fts, rowid, content) VALUES ('delete', old.id, '');
       END`,
    );
    // Rebuild once on boot so pre-existing rows are indexed (keeps the index honest after restarts).
    await this.ds.query(`DELETE FROM audit_fts`);
    await this.ds.query(`INSERT INTO audit_fts(rowid, content) SELECT id, ${CONTENT} FROM audit_log`);
    this.mode = 'fts5';
  }

  private async setupPostgres(): Promise<void> {
    // Functional GIN index stays in sync automatically — no stored column or trigger to drift.
    await this.ds.query(`CREATE INDEX IF NOT EXISTS idx_audit_search ON audit_log USING GIN (to_tsvector('english', ${CONTENT}))`);
    this.mode = 'tsvector';
  }

  /** Search the decision history. Returns matched audit entries, most-relevant first. */
  async recall(query: string, limit = 10): Promise<RecallHit[]> {
    const q = query.trim();
    if (!q) return [];
    const cap = Math.min(Math.max(1, limit), 50);
    let ids: number[] = [];

    if (this.mode === 'fts5') {
      const tokens = q.match(/[\p{L}\p{N}_]+/gu) ?? [];
      if (!tokens.length) return [];
      const match = tokens.map((t) => `"${t}"*`).join(' OR ');
      const rows = await this.ds.query(`SELECT rowid AS id FROM audit_fts WHERE audit_fts MATCH ? ORDER BY bm25(audit_fts) LIMIT ?`, [match, cap]);
      ids = rows.map((r: { id: number }) => r.id);
    } else if (this.mode === 'tsvector') {
      const rows = await this.ds.query(
        `SELECT id FROM audit_log WHERE to_tsvector('english', ${CONTENT}) @@ plainto_tsquery('english', $1)
         ORDER BY ts_rank(to_tsvector('english', ${CONTENT}), plainto_tsquery('english', $1)) DESC LIMIT $2`,
        [q, cap],
      );
      ids = rows.map((r: { id: number }) => r.id);
    } else {
      const like = `%${q.replace(/[%_]/g, '')}%`;
      const rows = await this.ds.query(`SELECT id FROM audit_log WHERE (${CONTENT}) LIKE ? ORDER BY id DESC LIMIT ?`, [like, cap]);
      ids = rows.map((r: { id: number }) => r.id);
    }

    if (!ids.length) return [];
    const entries: RecallHit[] = await this.ds.query(
      `SELECT id, timestamp, action, domain, validation_status, query, this_hash FROM audit_log WHERE id IN (${ids.map(() => '?').join(',')})`,
      ids,
    );
    // Preserve the ranked order returned by the search.
    const order = new Map(ids.map((id, i) => [id, i]));
    return entries.sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
  }
}
