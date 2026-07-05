/**
 * Persistence for the hash-chained audit log. Read-last-hash → seal → insert.
 * Mirrors api/app/core/audit_store.py. Append-only: never UPDATE/DELETE audit_log.
 *
 * Note: the Nest app owns its own chain; hashes are internally consistent (verifyChain),
 * not required to be byte-identical to a Python-generated chain.
 */
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { AuditLog } from '../common/shared.entities';
import { AuditCore, AuditEntry, GENESIS_HASH, makeEntry, verifyChain } from './audit';

@Injectable()
export class AuditService {
  constructor(@InjectRepository(AuditLog) private readonly repo: Repository<AuditLog>) {}

  // Serialize read-last-hash → insert so two concurrent folds can't read the same prev_hash and
  // fork the chain. ponytail: in-process promise chain (single API instance); the UNIQUE(prev_hash)
  // index on audit_log is the durable backstop that makes a cross-instance fork fail loud.
  private tail: Promise<unknown> = Promise.resolve();

  private async lastHash(): Promise<string> {
    const row = await this.repo.findOne({ where: {}, order: { id: 'DESC' } });
    return row?.this_hash ?? GENESIS_HASH;
  }

  async append(core: AuditCore): Promise<AuditEntry> {
    const run = this.tail.then(() => this.appendSerial(core));
    // Keep the chain alive even if one append rejects; callers still see their own error.
    this.tail = run.catch(() => undefined);
    return run;
  }

  private async appendSerial(core: AuditCore): Promise<AuditEntry> {
    const prev = await this.lastHash();
    const entry = makeEntry(prev, core);
    await this.repo.save(
      this.repo.create({
        timestamp: entry.timestamp,
        action: entry.action,
        domain: entry.domain,
        user_id: entry.user_id,
        query: entry.query,
        intent_global: entry.intent_global !== null ? JSON.stringify(entry.intent_global) : null,
        intent_domain: entry.intent_domain !== null ? JSON.stringify(entry.intent_domain) : null,
        validation_status: entry.validation_status,
        rules_version: entry.rules_version,
        prev_hash: entry.prev_hash,
        this_hash: entry.this_hash,
      }),
    );
    return entry;
  }

  async loadChain(): Promise<AuditEntry[]> {
    const rows = await this.repo.find({ order: { id: 'ASC' } });
    return rows.map((r) => ({
      timestamp: r.timestamp,
      action: r.action,
      domain: r.domain,
      user_id: r.user_id,
      query: r.query,
      intent_global: r.intent_global ? JSON.parse(r.intent_global) : null,
      intent_domain: r.intent_domain ? JSON.parse(r.intent_domain) : null,
      validation_status: r.validation_status ?? '',
      rules_version: r.rules_version,
      prev_hash: r.prev_hash ?? GENESIS_HASH,
      this_hash: r.this_hash ?? '',
    }));
  }

  async verify(): Promise<boolean> {
    return verifyChain(await this.loadChain());
  }
}
