/** Request DTOs for the tax API. Money in paise. Mirrors api/app/domains/tax/schemas.py. */
import { IsArray, IsInt, IsOptional, IsString } from 'class-validator';

export class TdsReturnInputDto {
  @IsString() return_type: string; // 24Q / 26Q / 27Q
  @IsString() quarter: string; // "2026-Q1"
  @IsString() due_date: string;
  @IsInt() total_deducted: number; // paise
  @IsString() @IsOptional() filed_date?: string | null;
}

export class Interest234cInputDto {
  @IsInt() total_liability: number; // paise
  @IsArray() @IsInt({ each: true }) cumulative_paid: number[]; // 4 cumulative amounts, paise
}
