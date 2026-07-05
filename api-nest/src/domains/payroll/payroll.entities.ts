/** Payroll domain tables (PRD §3.5). Money columns are BIGINT paise. Mirrors app/db/models/payroll.py. */
import { Column, Entity, Index, PrimaryGeneratedColumn } from 'typeorm';
import { moneyColumn } from '../../common/money';

@Entity('employees')
export class Employee {
  @PrimaryGeneratedColumn() id: number;
  @Column({ unique: true }) employee_code: string;
  @Column() name: string;
  @Column({ type: 'text', nullable: true }) email: string | null;
  @Column({ type: 'text', nullable: true }) phone: string | null;
  @Column({ type: 'text', nullable: true }) pan: string | null;
  @Column({ type: 'text', nullable: true }) uan: string | null;
  @Column({ type: 'text', nullable: true }) esi_ip_number: string | null;
  @Column() date_of_joining: string;
  @Column({ type: 'text', nullable: true }) date_of_exit: string | null;
  @Column({ default: 'active' }) status: string;
  @Column({ type: 'text', nullable: true }) state: string | null; // for PT/LWF state rules
  @Column({ type: 'text', nullable: true }) bank_account: string | null;
  @Column({ type: 'text', nullable: true }) ifsc: string | null;
}

@Entity('salary_structures')
export class SalaryStructure {
  @PrimaryGeneratedColumn() id: number;
  @Index() @Column({ type: 'integer' }) employee_id: number;
  @Column() effective_from: string;
  @Column(moneyColumn()) basic: number; // paise (monthly)
  @Column(moneyColumn()) hra: number;
  @Column(moneyColumn({ default: 0 })) lta: number;
  @Column(moneyColumn({ default: 0 })) special_allowance: number;
  @Column(moneyColumn()) employer_pf: number;
  @Column(moneyColumn({ default: 0 })) employer_esi: number;
  @Column(moneyColumn()) employee_pf: number;
  @Column(moneyColumn({ default: 0 })) employee_esi: number;
  @Column(moneyColumn({ default: 0 })) professional_tax: number;
  @Column(moneyColumn({ default: 0 })) tds_monthly: number;
  @Column(moneyColumn()) gross_salary: number;
  @Column(moneyColumn()) net_salary: number;
  @Column(moneyColumn()) ctc: number;
}

@Entity('payroll_runs')
export class PayrollRun {
  @PrimaryGeneratedColumn() id: number;
  @Column() month_year: string; // e.g. "2026-06"
  @Column() run_date: string;
  @Column(moneyColumn({ default: 0 })) total_gross: number;
  @Column(moneyColumn({ default: 0 })) total_deductions: number;
  @Column(moneyColumn({ default: 0 })) total_net: number;
  @Column(moneyColumn({ default: 0 })) total_pf_employer: number;
  @Column(moneyColumn({ default: 0 })) total_esi_employer: number;
  @Column({ default: 'draft' }) status: string;
  @Column({ type: 'integer', default: 0 }) ecr_generated: number;
  @Column({ type: 'text', nullable: true }) ecr_file_path: string | null;
}

@Entity('payroll_entries')
export class PayrollEntry {
  @PrimaryGeneratedColumn() id: number;
  @Index() @Column({ type: 'integer' }) payroll_run_id: number;
  @Index() @Column({ type: 'integer' }) employee_id: number;
  @Column(moneyColumn()) gross: number;
  @Column(moneyColumn()) basic: number;
  @Column(moneyColumn()) hra: number;
  @Column(moneyColumn({ default: 0 })) lta: number;
  @Column(moneyColumn({ default: 0 })) special_allowance: number;
  @Column(moneyColumn()) employee_pf: number;
  @Column(moneyColumn({ default: 0 })) employee_esi: number;
  @Column(moneyColumn({ default: 0 })) professional_tax: number;
  @Column(moneyColumn({ default: 0 })) tds: number;
  @Column(moneyColumn({ default: 0 })) other_deductions: number;
  @Column(moneyColumn({ default: 0 })) employer_pf: number;
  @Column(moneyColumn({ default: 0 })) employer_esi: number;
  @Column(moneyColumn()) net_pay: number;
}

@Entity('esop_grants')
export class EsopGrant {
  @PrimaryGeneratedColumn() id: number;
  @Index() @Column({ type: 'integer' }) employee_id: number;
  @Column() grant_date: string;
  @Column() vesting_start_date: string;
  @Column({ type: 'integer', default: 12 }) cliff_months: number;
  @Column({ type: 'integer', default: 48 }) vesting_period_months: number;
  @Column({ type: 'integer' }) total_options: number;
  @Column(moneyColumn()) exercise_price: number; // paise
  @Column({ type: 'integer', default: 0 }) vested_options: number;
  @Column({ type: 'integer', default: 0 }) exercised_options: number;
  @Column({ type: 'integer', default: 0 }) forfeited_options: number;
}
