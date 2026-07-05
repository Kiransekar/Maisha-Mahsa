/**
 * Semantic (hot-layer) memory, per organization. One row per (company_id, kind). Hard-capped in
 * chars by the service — durable facts only, never computed numbers (the Golden-Rule memory law).
 */
import { Column, Entity, Index, PrimaryGeneratedColumn, UpdateDateColumn } from 'typeorm';

@Entity('org_memory')
@Index(['company_id', 'kind'], { unique: true })
export class OrgMemory {
  @PrimaryGeneratedColumn() id: number;
  // Isolation boundary. Defaults to the single company in a per-deployment install; ready for multi-tenant.
  @Column({ type: 'integer', default: 1 }) company_id: number;
  @Column() kind: string; // 'cfo' = the agent's learned posture/preferences for this org
  @Column({ type: 'text', default: '' }) content: string;
  @UpdateDateColumn() updated_at: Date;
}

/**
 * Superseded versions of the hot layer. Memory Evolution is *non-destructive* (survey §5.2/§7.7):
 * an update archives the prior content with a timestamp rather than overwriting it, so history is
 * never lost and every change is auditable. Forgetting = archival, never a hard delete.
 */
@Entity('org_memory_history')
@Index(['company_id', 'kind'])
export class OrgMemoryHistory {
  @PrimaryGeneratedColumn() id: number;
  @Column({ type: 'integer', default: 1 }) company_id: number;
  @Column() kind: string;
  @Column({ type: 'text', default: '' }) content: string;
  @Column() superseded_at: string;
}
