/** Revenue domain tables (PRD §3.3). Money columns are BIGINT paise. Mirrors api/app/db/models/revenue.py. */
import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';
import { moneyColumn } from '../../common/money';

@Entity('customers')
export class Customer {
  @PrimaryGeneratedColumn() id: number;
  @Column() name: string;
  @Column({ type: 'text', nullable: true }) pan: string | null;
  @Column({ type: 'text', nullable: true }) gstin: string | null;
  @Column({ type: 'text', nullable: true }) email: string | null;
  @Column({ type: 'text', nullable: true }) phone: string | null;
  @Column({ type: 'text', nullable: true }) address: string | null;
  @Column({ type: 'text', nullable: true }) state: string | null; // place of supply
  @Column({ type: 'integer', default: 30 }) payment_terms: number; // days
  @Column({ type: 'integer', default: 0 }) tds_applicable: number;
  @Column({ type: 'text', nullable: true }) tds_section: string | null;
  @Column({ type: 'float', default: 0.0 }) tds_rate: number;
  @Column({ type: 'text', nullable: true }) created_at: string;
}

@Entity('invoices')
export class Invoice {
  @PrimaryGeneratedColumn() id: number;
  @Column({ unique: true }) invoice_number: string;
  @Column({ type: 'integer' }) customer_id: number;
  @Column() invoice_date: string;
  @Column() due_date: string;
  @Column(moneyColumn()) subtotal: number; // paise (taxable)
  @Column({ type: 'float', default: 0.0 }) gst_rate: number;
  @Column(moneyColumn({ default: 0 })) igst_amount: number;
  @Column(moneyColumn({ default: 0 })) cgst_amount: number;
  @Column(moneyColumn({ default: 0 })) sgst_amount: number;
  @Column(moneyColumn()) total_amount: number;
  @Column(moneyColumn({ default: 0 })) tds_amount: number;
  @Column(moneyColumn()) net_receivable: number;
  @Column({ type: 'text', nullable: true }) irn: string | null;
  @Column({ type: 'text', nullable: true }) qr_code_path: string | null;
  @Column({ default: 'draft' }) status: string;
  @Column({ type: 'text', nullable: true }) paid_date: string | null;
  @Column(moneyColumn({ default: 0 })) paid_amount: number;
}

@Entity('invoice_items')
export class InvoiceItem {
  @PrimaryGeneratedColumn() id: number;
  @Column({ type: 'integer' }) invoice_id: number;
  @Column() description: string;
  @Column({ type: 'text', nullable: true }) hsn_code: string | null;
  @Column({ type: 'integer', default: 1 }) quantity: number;
  @Column(moneyColumn()) rate: number; // paise per unit
  @Column(moneyColumn()) amount: number; // paise
}

@Entity('credit_notes')
export class CreditNote {
  @PrimaryGeneratedColumn() id: number;
  @Column({ unique: true }) credit_note_number: string;
  @Column({ type: 'integer' }) invoice_id: number;
  @Column() issue_date: string;
  @Column({ type: 'text', nullable: true }) reason: string | null;
  @Column(moneyColumn()) amount: number; // paise
  @Column(moneyColumn({ default: 0 })) gst_adjustment: number;
}
