/** Treasury domain tables (PRD §3.2). Money columns are BIGINT paise. Mirrors api/app/db/models/treasury.py. */
import { Column, Entity, Index, PrimaryGeneratedColumn } from 'typeorm';
import { moneyColumn } from '../../common/money';

@Entity('bank_accounts')
export class BankAccount {
  @PrimaryGeneratedColumn() id: number;
  @Column() bank_name: string;
  @Column() account_number: string;
  @Column() ifsc: string;
  @Column({ type: 'text', nullable: true }) account_type: string | null;
  @Column(moneyColumn({ default: 0 })) opening_balance: number; // paise
  @Column(moneyColumn({ default: 0 })) current_balance: number; // paise
  @Column({ default: 'INR' }) currency: string;
  @Column({ type: 'integer', default: 0 }) is_primary: number;
  @Column({ type: 'text', nullable: true }) last_sync: string | null;
}

@Entity('bank_transactions')
export class BankTransaction {
  @PrimaryGeneratedColumn() id: number;
  @Index() @Column({ type: 'integer' }) account_id: number;
  @Column() txn_date: string;
  @Column({ type: 'text', nullable: true }) description: string | null;
  @Column({ type: 'text', nullable: true }) reference: string | null;
  @Column(moneyColumn({ default: 0 })) debit: number; // paise
  @Column(moneyColumn({ default: 0 })) credit: number; // paise
  @Column(moneyColumn({ nullable: true })) balance: number | null; // paise
  @Column({ type: 'text', nullable: true }) category: string | null;
  @Column({ type: 'integer', nullable: true }) matched_invoice_id: number | null;
  @Column({ type: 'integer', nullable: true }) matched_vendor_id: number | null;
  @Column({ type: 'integer', default: 0 }) is_reconciled: number;
}

@Entity('fixed_deposits')
export class FixedDeposit {
  @PrimaryGeneratedColumn() id: number;
  @Column({ type: 'integer', nullable: true }) bank_account_id: number | null;
  @Column() fd_number: string;
  @Column(moneyColumn()) principal: number; // paise
  @Column({ type: 'float' }) interest_rate: number;
  @Column() start_date: string;
  @Column() maturity_date: string;
  @Column(moneyColumn({ nullable: true })) maturity_amount: number | null; // paise
  @Column(moneyColumn({ default: 0 })) tds_deducted: number; // paise
  @Column({ default: 'active' }) status: string;
}
