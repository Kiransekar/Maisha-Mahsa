/**
 * Experiential memory evolution: which tax strategies this org has adopted or dismissed. The
 * optimizer reads this to stop re-surfacing rejected moves — cumulative learning, deterministic and
 * auditable (each decision is sealed to the audit chain). One row per (company_id, playbook_id).
 */
import { Column, Entity, Index, PrimaryGeneratedColumn } from 'typeorm';

@Entity('playbook_feedback')
@Index(['company_id', 'playbook_id'], { unique: true })
export class PlaybookFeedback {
  @PrimaryGeneratedColumn() id: number;
  @Column({ type: 'integer', default: 1 }) company_id: number;
  @Column() playbook_id: string;
  @Column() decision: string; // 'adopted' | 'dismissed'
  @Column() at: string;
}
