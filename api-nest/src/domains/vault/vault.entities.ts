/**
 * Document vault table (PRD §3.1 / §1.12). Mirrors api/app/db/models/vault.py.
 * The id IS the SHA-256 of content. No money columns in this domain.
 */
import { Column, CreateDateColumn, Entity, PrimaryColumn } from 'typeorm';

@Entity('documents')
export class Document {
  @PrimaryColumn() id: string; // SHA-256 of content
  @Column() file_name: string;
  @Column() file_path: string;
  @Column() doc_type: string;
  @Column({ type: 'text', nullable: true }) domain: string | null;
  @Column({ type: 'text', nullable: true }) entity_id: string | null;
  @Column({ type: 'text', nullable: true }) ocr_text: string | null;
  @Column() upload_date: string;
  @Column({ type: 'text', nullable: true }) retention_until: string | null; // null = permanent
  @Column() sha256: string;
  @Column({ type: 'text', nullable: true }) tags: string | null;
  @Column({ type: 'text', nullable: true }) uploaded_by: string | null;
  @Column({ type: 'integer', default: 1 }) version: number;
  @CreateDateColumn() created_at: Date;
}
