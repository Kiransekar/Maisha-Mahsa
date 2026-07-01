/** Request DTOs for the ledger API. Money in paise. Mirrors api/app/domains/ledger/schemas.py. */
import { Type } from 'class-transformer';
import { IsArray, IsInt, IsOptional, IsString, ValidateNested } from 'class-validator';

export class NewAccountDto {
  @IsString() code: string;
  @IsString() name: string;
  @IsString() account_type: string; // asset/liability/equity/income/expense
  @IsString() @IsOptional() sub_type?: string | null;
  @IsInt() @IsOptional() opening_balance = 0;
}

export class JournalLineInputDto {
  @IsInt() account_id: number;
  @IsInt() @IsOptional() debit = 0;
  @IsInt() @IsOptional() credit = 0;
  @IsString() @IsOptional() description?: string | null;
}

export class NewJournalEntryDto {
  @IsString() entry_date: string;
  @IsString() description: string;
  @IsString() @IsOptional() reference?: string | null;
  @IsString() @IsOptional() source = 'manual';
  @IsArray() @ValidateNested({ each: true }) @Type(() => JournalLineInputDto) lines: JournalLineInputDto[] = [];
}
