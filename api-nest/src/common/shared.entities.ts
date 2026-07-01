/** Shared tables (PRD §3.1). Money columns are BIGINT paise. Mirrors api/app/db/models/shared.py. */
import { Column, CreateDateColumn, Entity, PrimaryGeneratedColumn } from 'typeorm';
import { moneyColumn } from './money';

@Entity('company')
export class Company {
  @PrimaryGeneratedColumn() id: number;
  @Column() name: string;
  @Column({ type: 'text', nullable: true, unique: true }) cin: string | null;
  @Column({ unique: true }) pan: string;
  @Column({ type: 'text', nullable: true, unique: true }) gstin: string | null;
  @Column({ type: 'text', nullable: true }) incorporation_date: string | null;
  @Column({ default: '03-31' }) financial_year_end: string;
  @Column({ type: 'text', nullable: true }) msme_registration: string | null;
  @Column({ type: 'text', nullable: true }) dpiit_recognition: string | null;
  @Column({ type: 'text', nullable: true }) sector: string | null;
  @Column({ type: 'text', nullable: true }) address: string | null;
  @Column({ type: 'text', nullable: true }) state: string | null;
  @CreateDateColumn() created_at: Date;
}

@Entity('users')
export class User {
  @PrimaryGeneratedColumn('uuid') id: string;
  @Column({ unique: true }) email: string;
  @Column({ type: 'text', nullable: true }) name: string | null;
  @Column({ default: 'founder' }) role: string;
  @Column({ default: 'founder' }) expertise: string;
  @CreateDateColumn() created_at: Date;
}

/** Append-only, hash-chained (PRD §11.2). Application code must never UPDATE/DELETE. */
@Entity('audit_log')
export class AuditLog {
  @PrimaryGeneratedColumn() id: number;
  @Column() timestamp: string;
  @Column() action: string;
  @Column() domain: string;
  @Column() user_id: string;
  @Column({ type: 'text', nullable: true }) query: string | null;
  @Column({ type: 'text', nullable: true }) intent_global: string | null; // JSON array
  @Column({ type: 'text', nullable: true }) intent_domain: string | null; // JSON array
  @Column({ type: 'text', nullable: true }) validation_status: string | null;
  @Column() rules_version: string;
  @Column({ type: 'text', nullable: true }) prev_hash: string | null;
  @Column({ type: 'text', nullable: true }) this_hash: string | null;
}

@Entity('llm_trace')
export class LlmTrace {
  @PrimaryGeneratedColumn() id: number;
  @Column() timestamp: string;
  @Column() domain: string;
  @Column({ type: 'text', nullable: true }) audit_hash: string | null;
  @Column() model_label: string;
  @Column() input_sha256: string;
  @Column({ type: 'text', nullable: true }) claim_sha256: string | null;
  @Column({ default: 1 }) attempts: number;
  @Column({ default: 0 }) verified: number;
  @Column({ default: 0 }) requires_approval: number;
  @Column({ default: 0 }) latency_ms: number;
}

@Entity('metric_snapshot')
export class MetricSnapshot {
  @PrimaryGeneratedColumn() id: number;
  @Column() captured_at: string;
  @Column() domain: string;
  @Column() metric: string;
  @Column({ type: 'double precision' }) value: number; // observability only, float ok
}

/** A human approve/reject on a flagged domain state (F4). Keyed by state_hash. */
@Entity('decision')
export class Decision {
  @PrimaryGeneratedColumn() id: number;
  @Column() timestamp: string;
  @Column() domain: string;
  @Column() decision: string; // "approved" | "rejected"
  @Column() state_hash: string;
  @Column({ type: 'text', nullable: true }) audit_hash: string | null;
  @Column() user_id: string;
}

@Entity('compliance_calendar')
export class ComplianceCalendar {
  @PrimaryGeneratedColumn() id: number;
  @Column() domain: string;
  @Column() form_name: string;
  @Column() due_date: string;
  @Column({ type: 'text', nullable: true }) filing_period: string | null;
  @Column({ default: 'pending' }) status: string;
  @Column({ type: 'text', nullable: true }) filed_date: string | null;
  @Column({ type: 'text', nullable: true }) acknowledgement: string | null;
  @Column(moneyColumn({ default: 0 })) penalty_amount: number; // paise
  @Column({ default: 0 }) reminder_sent: number;
  @CreateDateColumn() created_at: Date;
}

@Entity('rules_registry')
export class RulesRegistry {
  @PrimaryGeneratedColumn() id: number;
  @Column() version: string;
  @Column() domain: string;
  @Column({ unique: true }) rule_id: string;
  @Column({ type: 'text' }) description: string;
  @Column({ type: 'text', nullable: true }) statute: string | null;
  @Column({ type: 'text', nullable: true }) section: string | null;
  @Column({ type: 'text', nullable: true }) condition_logic: string | null;
  @Column({ default: 'warning' }) severity: string;
  @Column({ default: 1 }) active: number;
  @CreateDateColumn() created_at: Date;
}

export const SHARED_ENTITIES = [
  Company,
  User,
  AuditLog,
  LlmTrace,
  MetricSnapshot,
  Decision,
  ComplianceCalendar,
  RulesRegistry,
];
