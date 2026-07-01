/** Expense domain tables (PRD §3.11). Money columns are BIGINT paise. Mirrors api/app/db/models/expense.py. */
import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';
import { moneyColumn } from '../../common/money';

@Entity('expense_claims')
export class ExpenseClaim {
  @PrimaryGeneratedColumn() id: number;
  @Column({ type: 'integer', nullable: true }) employee_id: number | null;
  @Column() claim_date: string;
  @Column() expense_date: string;
  @Column() category: string;
  @Column(moneyColumn()) amount: number; // paise
  @Column(moneyColumn({ default: 0 })) gst_amount: number; // paise
  @Column({ type: 'text', nullable: true }) vendor_name: string | null;
  @Column({ type: 'text', nullable: true }) description: string | null;
  @Column({ type: 'text', nullable: true }) receipt_document_id: string | null;
  @Column({ type: 'integer', default: 0 }) over_policy: number;
  @Column({ default: 'submitted' }) status: string;
  @Column({ type: 'text', nullable: true }) approved_by: string | null;
  @Column({ type: 'text', nullable: true }) approved_date: string | null;
  @Column({ type: 'text', nullable: true }) reimbursement_date: string | null;
}
