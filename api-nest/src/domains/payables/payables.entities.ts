/** Payables domain tables (PRD §3.4). Money columns are BIGINT paise. Mirrors api/app/db/models/payables.py. */
import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';
import { moneyColumn } from '../../common/money';

@Entity('vendors')
export class Vendor {
  @PrimaryGeneratedColumn() id: number;
  @Column() name: string;
  @Column({ type: 'text', nullable: true }) pan: string | null;
  @Column({ type: 'text', nullable: true }) gstin: string | null;
  @Column({ type: 'integer', default: 0 }) msme_status: number; // 1 = registered MSME
  @Column({ type: 'text', nullable: true }) msme_type: string | null; // micro/small/medium
  @Column({ type: 'text', nullable: true }) bank_account: string | null;
  @Column({ type: 'text', nullable: true }) ifsc: string | null;
  @Column({ type: 'integer', default: 30 }) payment_terms: number; // days
  @Column({ type: 'text', nullable: true }) tds_section: string | null; // 194C/194J/194H/194I
  @Column({ default: 'company' }) payee_type: string; // individual/huf/company
}

@Entity('purchase_orders')
export class PurchaseOrder {
  @PrimaryGeneratedColumn() id: number;
  @Column({ unique: true }) po_number: string;
  @Column({ type: 'integer' }) vendor_id: number;
  @Column() po_date: string;
  @Column({ type: 'text', nullable: true }) delivery_date: string | null;
  @Column(moneyColumn()) total_amount: number; // paise
  @Column(moneyColumn({ default: 0 })) received_amount: number; // GRN value, paise
  @Column({ default: 'open' }) status: string;
}

@Entity('bills')
export class Bill {
  @PrimaryGeneratedColumn() id: number;
  @Column() bill_number: string;
  @Column({ type: 'integer' }) vendor_id: number;
  @Column({ type: 'integer', nullable: true }) po_id: number | null;
  @Column() bill_date: string;
  @Column() due_date: string;
  @Column(moneyColumn()) subtotal: number; // paise (taxable)
  @Column(moneyColumn({ default: 0 })) gst_amount: number;
  @Column(moneyColumn({ default: 0 })) igst_amount: number;
  @Column(moneyColumn({ default: 0 })) cgst_amount: number;
  @Column(moneyColumn({ default: 0 })) sgst_amount: number;
  @Column(moneyColumn({ default: 0 })) tds_amount: number;
  @Column(moneyColumn()) total_amount: number;
  @Column({ type: 'integer', default: 1 }) itc_eligible: number;
  @Column({ default: 'open' }) status: string;
  @Column({ type: 'text', nullable: true }) paid_date: string | null;
  @Column(moneyColumn({ default: 0 })) paid_amount: number;
}
