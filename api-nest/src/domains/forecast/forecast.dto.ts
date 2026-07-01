/** Request DTOs for the forecast API. Money in paise. Mirrors api/app/domains/forecast/schemas.py. */
import { IsArray, IsInt, IsNumber, IsOptional, IsString } from 'class-validator';

export class CashProjectionInputDto {
  @IsInt() opening_cash: number; // paise
  @IsArray() @IsInt({ each: true }) @IsOptional() monthly_net_change: number[] = []; // signed paise/month
}

export class ScenarioInputDto {
  @IsInt() opening_cash: number;
  @IsInt() base_revenue: number; // monthly paise
  @IsInt() base_cost: number; // monthly paise
  @IsInt() @IsOptional() horizon_months = 12;
  @IsNumber() @IsOptional() revenue_mult = 1.0;
  @IsInt() @IsOptional() extra_cost = 0; // e.g. extra hires per month
}

export class UnitEconomicsInputDto {
  @IsInt() sales_marketing_spend: number; // paise
  @IsInt() new_customers: number;
  @IsInt() arpu: number; // monthly paise per account
  @IsNumber() gross_margin: number; // fraction
  @IsInt() lifetime_months: number;
}

export class RecordForecastDto {
  @IsString() forecast_date: string;
  @IsString() @IsOptional() scenario = 'base';
  @IsInt() @IsOptional() horizon_months = 12;
  @IsInt() opening_cash: number;
  @IsArray() @IsInt({ each: true }) @IsOptional() monthly_net_change: number[] = [];
}
