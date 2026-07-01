/** Request DTOs for the payroll API. Money in paise. Mirrors app/domains/payroll/schemas.py. */
import { IsInt, IsOptional, IsString } from 'class-validator';

export class NewEmployeeDto {
  @IsString() employee_code: string;
  @IsString() name: string;
  @IsString() date_of_joining: string; // ISO date
  @IsString() @IsOptional() state?: string | null; // for PT
  @IsString() @IsOptional() pan?: string | null;
  @IsString() @IsOptional() uan?: string | null;
}

/** Monthly component inputs in paise. Statutory deductions are derived, not supplied. */
export class SalaryInputDto {
  @IsString() effective_from: string;
  @IsInt() basic: number;
  @IsInt() hra: number;
  @IsInt() @IsOptional() lta = 0;
  @IsInt() @IsOptional() special_allowance = 0;
}
