/** Equity domain tables (PRD §3.9). Money columns are BIGINT paise; share counts are plain
 * integers. Mirrors api/app/db/models/equity.py. */
import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';
import { moneyColumn } from '../../common/money';

@Entity('shareholders')
export class Shareholder {
  @PrimaryGeneratedColumn() id: number;
  @Column() name: string;
  @Column() category: string; // founder/investor/esop/advisor
  @Column({ type: 'text', nullable: true }) pan: string | null;
  @Column({ type: 'text', nullable: true }) email: string | null;
  @Column({ type: 'text', nullable: true }) investment_date: string | null;
  @Column(moneyColumn({ default: 0 })) investment_amount: number; // paise
  @Column({ type: 'text', nullable: true }) share_class: string | null;
  @Column({ type: 'integer', default: 0 }) shares_held: number;
  @Column(moneyColumn({ default: 0 })) share_premium: number; // paise
  @Column(moneyColumn({ nullable: true })) pre_money_valuation: number | null; // paise
  @Column(moneyColumn({ nullable: true })) post_money_valuation: number | null; // paise
  @Column({ type: 'text', nullable: true }) anti_dilution: string | null;
  @Column({ type: 'float', nullable: true }) liquidation_preference: number | null;
  @Column({ type: 'integer', default: 0 }) board_seat: number;
}

@Entity('safe_notes')
export class SafeNote {
  @PrimaryGeneratedColumn() id: number;
  @Column({ type: 'integer' }) investor_id: number;
  @Column() issue_date: string;
  @Column(moneyColumn()) investment_amount: number; // paise
  @Column(moneyColumn({ nullable: true })) valuation_cap: number | null; // paise
  @Column({ type: 'float', default: 0.0 }) discount_rate: number; // e.g. 0.20
  @Column({ type: 'integer', default: 1 }) pro_rata_rights: number;
  @Column({ type: 'text', nullable: true }) conversion_trigger: string | null;
  @Column({ type: 'integer', default: 0 }) converted: number;
  @Column({ type: 'text', nullable: true }) conversion_date: string | null;
  @Column({ type: 'integer', nullable: true }) shares_issued: number | null;
}

@Entity('cap_table_snapshots')
export class CapTableSnapshot {
  @PrimaryGeneratedColumn() id: number;
  @Column() snapshot_date: string;
  @Column({ type: 'integer' }) total_shares: number;
  @Column({ type: 'integer' }) total_diluted_shares: number;
  @Column({ type: 'integer', default: 0 }) esop_pool_shares: number;
  @Column({ type: 'float', default: 0.0 }) esop_pool_pct: number;
  @Column({ type: 'integer', default: 1 }) esop_board_approved: number;
  @Column() snapshot_json: string;
}
