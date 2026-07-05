/** Ledger / accounting tables (PRD §3.8). Money columns are BIGINT paise. Mirrors api/app/db/models/ledger.py. */
import { Column, Entity, Index, PrimaryGeneratedColumn } from 'typeorm';
import { moneyColumn } from '../../common/money';

@Entity('chart_of_accounts')
export class ChartOfAccounts {
  @PrimaryGeneratedColumn() id: number;
  @Column({ unique: true }) code: string;
  @Column() name: string;
  @Column() account_type: string; // asset / liability / equity / income / expense
  @Column({ type: 'text', nullable: true }) sub_type: string | null;
  @Column({ type: 'integer', nullable: true }) parent_id: number | null;
  @Column({ type: 'integer', default: 0 }) is_bank_account: number;
  @Column({ type: 'integer', default: 0 }) is_cash_account: number;
  @Column(moneyColumn({ default: 0 })) opening_balance: number; // paise
}

@Entity('journal_entries')
export class JournalEntry {
  @PrimaryGeneratedColumn() id: number;
  @Column() entry_date: string;
  @Column({ type: 'text', nullable: true }) reference: string | null;
  @Column() description: string;
  @Column({ type: 'text', nullable: true }) source: string | null; // manual / payroll / gst / depreciation
  @Column(moneyColumn()) total_debit: number; // paise
  @Column(moneyColumn()) total_credit: number; // paise
  @Column({ type: 'integer', default: 0 }) is_auto_generated: number;
  @Column({ type: 'text', nullable: true }) created_at: string | null;
}

@Entity('journal_lines')
export class JournalLine {
  @PrimaryGeneratedColumn() id: number;
  @Index() @Column({ type: 'integer' }) journal_entry_id: number;
  @Index() @Column({ type: 'integer' }) account_id: number;
  @Column(moneyColumn({ default: 0 })) debit: number; // paise
  @Column(moneyColumn({ default: 0 })) credit: number; // paise
  @Column({ type: 'text', nullable: true }) description: string | null;
}

@Entity('fixed_assets')
export class FixedAsset {
  @PrimaryGeneratedColumn() id: number;
  @Column() asset_name: string;
  @Column({ type: 'text', nullable: true }) asset_code: string | null;
  @Column() purchase_date: string;
  @Column(moneyColumn()) purchase_cost: number; // paise
  @Column(moneyColumn({ default: 0 })) salvage_value: number; // paise
  @Column({ type: 'integer' }) useful_life_years: number;
  @Column({ default: 'wdv' }) depreciation_method: string; // slm / wdv
  @Column({ type: 'float', default: 0.0 }) depreciation_rate: number; // for WDV
  @Column(moneyColumn({ default: 0 })) accumulated_depreciation: number; // paise
  @Column(moneyColumn()) wdv: number; // paise
  @Column({ type: 'text', nullable: true }) disposal_date: string | null;
  @Column(moneyColumn({ nullable: true })) disposal_amount: number | null; // paise
  @Column({ default: 'active' }) status: string;
}
