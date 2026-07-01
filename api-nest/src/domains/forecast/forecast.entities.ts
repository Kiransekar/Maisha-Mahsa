/** Forecast / budgeting tables (PRD §3.10). Money columns are BIGINT paise. Mirrors api/app/db/models/forecast.py. */
import { Column, Entity, PrimaryGeneratedColumn } from 'typeorm';
import { moneyColumn } from '../../common/money';

@Entity('budgets')
export class Budget {
  @PrimaryGeneratedColumn() id: number;
  @Column() fy: string;
  @Column() category: string;
  @Column({ type: 'text', nullable: true }) sub_category: string | null;
  @Column(moneyColumn({ default: 0 })) jan: number; // paise
  @Column(moneyColumn({ default: 0 })) feb: number;
  @Column(moneyColumn({ default: 0 })) mar: number;
  @Column(moneyColumn({ default: 0 })) apr: number;
  @Column(moneyColumn({ default: 0 })) may: number;
  @Column(moneyColumn({ default: 0 })) jun: number;
  @Column(moneyColumn({ default: 0 })) jul: number;
  @Column(moneyColumn({ default: 0 })) aug: number;
  @Column(moneyColumn({ default: 0 })) sep: number;
  @Column(moneyColumn({ default: 0 })) oct: number;
  @Column(moneyColumn({ default: 0 })) nov: number;
  @Column(moneyColumn({ default: 0 })) dec: number;
  @Column(moneyColumn()) annual_total: number;
}

@Entity('forecasts')
export class Forecast {
  @PrimaryGeneratedColumn() id: number;
  @Column() forecast_date: string;
  @Column({ type: 'integer', default: 12 }) horizon_months: number;
  @Column({ default: 'base' }) scenario: string;
  @Column(moneyColumn({ nullable: true })) revenue_forecast: number | null; // paise
  @Column(moneyColumn({ nullable: true })) burn_forecast: number | null; // paise/month
  @Column({ type: 'integer', nullable: true }) headcount_forecast: number | null;
  @Column(moneyColumn({ nullable: true })) cash_forecast: number | null; // projected min cash, paise
  @Column({ type: 'real', nullable: true }) runway_forecast: number | null; // months
  @Column({ type: 'text', nullable: true }) assumptions: string | null;
}
