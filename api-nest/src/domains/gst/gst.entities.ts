/** GST domain tables (PRD §3.6). Money columns are BIGINT paise. Mirrors api/app/db/models/gst.py. */
import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';
import { moneyColumn } from '../../common/money';

@Entity('gst_returns')
export class GstReturn {
  @PrimaryGeneratedColumn() id: number;
  @Column() return_type: string; // GSTR-1 / GSTR-3B / ...
  @Column() filing_period: string; // "YYYY-MM"
  @Column() due_date: string;
  @Column({ type: 'text', nullable: true }) filed_date: string | null;
  @Column({ default: 'pending' }) status: string;
  @Column({ type: 'text', nullable: true }) json_file_path: string | null;
  @Column({ type: 'text', nullable: true }) acknowledgement: string | null;
  @Column(moneyColumn({ default: 0 })) tax_payable: number; // paise (cash)
  @Column(moneyColumn({ default: 0 })) tax_paid: number;
  @Column(moneyColumn({ default: 0 })) late_fee: number;
  @Column(moneyColumn({ default: 0 })) interest: number;
}

@Entity('itc_register')
export class ItcRegister {
  @PrimaryGeneratedColumn() id: number;
  @Column({ type: 'integer', nullable: true }) invoice_id: number | null;
  @Column({ type: 'integer', nullable: true }) bill_id: number | null;
  @Column() gstin_supplier: string;
  @Column() invoice_number: string;
  @Column() invoice_date: string;
  @Column(moneyColumn()) taxable_value: number; // paise
  @Column(moneyColumn({ default: 0 })) igst: number;
  @Column(moneyColumn({ default: 0 })) cgst: number;
  @Column(moneyColumn({ default: 0 })) sgst: number;
  @Column(moneyColumn()) total_tax: number;
  @Column({ default: 1 }) eligible_itc: number; // 1 = eligible
  @Column({ default: 0 }) in_2b: number; // 1 = appears in GSTR-2B
  @Column({ type: 'text', nullable: true }) claimed_in_return: string | null;
}
