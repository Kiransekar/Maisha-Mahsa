/**
 * Vault service: document ingestion (content-hashed, deduped), classification, retention,
 * full-text search, integrity verification, RBAC, and the vault health snapshot for Mahsa.
 * Mirrors api/app/domains/vault/service.py. The document id IS its SHA-256, so re-ingesting
 * identical content is detected as a duplicate rather than stored twice.
 */
import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';

import { SnapshotProducer } from '../../core/loop.service';
import * as vault from './vault.calc';
import { IngestDocumentDto, IngestResult } from './vault.dto';
import { Document } from './vault.entities';

@Injectable()
export class VaultService implements SnapshotProducer {
  readonly domain = 'vault';

  constructor(
    @InjectRepository(Document) private readonly documents: Repository<Document>,
  ) {}

  // ---- ingestion ------------------------------------------------------------------

  async ingest(
    body: IngestDocumentDto & { upload_date: string },
  ): Promise<IngestResult> {
    const sha = vault.sha256Hex(body.content);
    const existing = await this.documents.findOne({ where: { id: sha } });
    if (existing !== null) {
      return {
        id: existing.id,
        sha256: existing.sha256,
        doc_type: existing.doc_type,
        retention_until: existing.retention_until,
        duplicate: true,
      };
    }

    const resolvedType = vault.classify(body.file_name, body.doc_type);
    const retain = vault.retentionUntil(body.upload_date, resolvedType);
    const doc = this.documents.create({
      id: sha,
      file_name: body.file_name,
      file_path: `vault/${sha}`,
      doc_type: resolvedType,
      domain: body.domain ?? null,
      entity_id: body.entity_id ?? null,
      ocr_text: body.content,
      upload_date: body.upload_date,
      retention_until: retain,
      sha256: sha,
      tags: body.tags ?? null,
      uploaded_by: body.uploaded_by ?? null,
      version: 1,
    });
    await this.documents.save(doc);
    return { id: sha, sha256: sha, doc_type: resolvedType, retention_until: retain, duplicate: false };
  }

  // ---- access ---------------------------------------------------------------------

  private async docs(): Promise<Record<string, any>[]> {
    const rows = await this.documents.find();
    return rows.map((d) => ({
      id: d.id,
      file_name: d.file_name,
      ocr_text: d.ocr_text,
      tags: d.tags,
      sha256: d.sha256,
      retention_until: d.retention_until,
    }));
  }

  async search(query: string): Promise<Record<string, any>[]> {
    return vault.search(await this.docs(), query);
  }

  async verifyIntegrity(docId: string, currentContent: string): Promise<boolean> {
    const doc = await this.documents.findOne({ where: { id: docId } });
    if (doc === null) throw new Error(`document ${docId} not found`);
    return vault.verifyIntegrity(doc.sha256, currentContent);
  }

  // ---- RBAC access control --------------------------------------------------------

  canAccess(role: string, action: string, sensitivity = 'internal'): boolean {
    return vault.canAccess(role, action, sensitivity);
  }

  async accessibleDocuments(role: string): Promise<Record<string, any>[]> {
    const out: Record<string, any>[] = [];
    for (const d of await this.documents.find()) {
      const sensitivity = vault.documentSensitivity(d.doc_type ?? 'other');
      if (vault.canAccess(role, 'read', sensitivity)) {
        out.push({ id: d.id, file_name: d.file_name, sensitivity });
      }
    }
    return out;
  }

  // ---- Mahsa contract -------------------------------------------------------------

  async buildSnapshot(asOf?: string): Promise<Record<string, any>> {
    const anchor = asOf ?? '1970-01-01';
    const metrics = vault.buildMetrics(await this.docs(), anchor);
    return { as_of: anchor, metrics };
  }
}
