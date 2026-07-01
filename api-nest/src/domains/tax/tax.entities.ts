/** Tax domain tables (PRD §3.7). Money columns are BIGINT paise. Mirrors api/app/db/models/tax.py. */
import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';
import { moneyColumn } from '../../common/money';

@Entity('tds_returns')
export class TdsReturn {
  @PrimaryGeneratedColumn() id: number;
  @Column() return_type: string; // 24Q / 26Q / 27Q
  @Column() quarter: string; // e.g. "2026-Q1"
  @Column() due_date: string;
  @Column({ type: 'text', nullable: true }) filed_date: string | null;
  @Column({ default: 'pending' }) status: string;
  @Column(moneyColumn({ default: 0 })) total_deducted: number; // paise
  @Column(moneyColumn({ default: 0 })) total_deposited: number;
  @Column(moneyColumn({ default: 0 })) late_filing_fee: number;
  @Column({ type: 'text', nullable: true }) json_file_path: string | null;
}

@Entity('tds_entries')
export class TdsEntry {
  @PrimaryGeneratedColumn() id: number;
  @Column({ type: 'integer', nullable: true }) tds_return_id: number | null;
  @Column() deductee_name: string;
  @Column({ type: 'text', nullable: true }) deductee_pan: string | null;
  @Column() section: string;
  @Column() payment_date: string;
  @Column(moneyColumn()) payment_amount: number; // paise
  @Column({ type: 'float', default: 0 }) tds_rate: number;
  @Column(moneyColumn()) tds_amount: number; // paise
  @Column(moneyColumn({ default: 0 })) surcharge: number;
  @Column(moneyColumn({ default: 0 })) cess: number;
  @Column(moneyColumn()) total_tds: number;
  @Column({ type: 'text', nullable: true }) deposit_date: string | null;
  @Column({ type: 'text', nullable: true }) challan_number: string | null;
  @Column({ type: 'text', nullable: true }) bsr_code: string | null;
}

@Entity('advance_tax')
export class AdvanceTax {
  @PrimaryGeneratedColumn() id: number;
  @Column() fy: string; // e.g. "2026-27"
  @Column() installment: string; // Q1/Q2/Q3/Q4
  @Column() due_date: string;
  @Column({ type: 'text', nullable: true }) paid_date: string | null;
  @Column(moneyColumn()) amount: number; // paise
  @Column({ type: 'text', nullable: true }) challan_number: string | null;
  @Column({ type: 'text', nullable: true }) bsr_code: string | null;
  @Column({ default: 'pending' }) status: string;
}
