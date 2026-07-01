/** Request DTOs for the treasury API. Money in paise. Mirrors api/app/domains/treasury/{schemas,router}.py. */
import { IsInt, IsOptional, IsString } from 'class-validator';

export class NewAccountDto {
  @IsString() bank_name: string;
  @IsString() account_number: string;
  @IsString() ifsc: string;
  @IsInt() @IsOptional() opening_balance_paise = 0;
}

/** Raw bank-statement CSV text to import (the Python route reads an UploadFile). */
export class ImportCsvDto {
  @IsString() csv_text: string;
}
