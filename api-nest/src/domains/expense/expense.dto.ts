/** Request DTOs for the expense API. Money in paise. Mirrors api/app/domains/expense/schemas.py. */
import { IsInt, IsOptional, IsString } from 'class-validator';

export class NewClaimDto {
  @IsInt() @IsOptional() employee_id?: number | null;
  @IsString() claim_date: string;
  @IsString() expense_date: string;
  @IsString() category: string;
  @IsInt() amount: number; // paise
  @IsInt() @IsOptional() gst_amount = 0;
  @IsString() @IsOptional() vendor_name?: string | null;
  @IsString() @IsOptional() description?: string | null;
}

export class ReceiptTextDto {
  @IsString() ocr_text: string;
}
