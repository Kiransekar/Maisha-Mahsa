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
