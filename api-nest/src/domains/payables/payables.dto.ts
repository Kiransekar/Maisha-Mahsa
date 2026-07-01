/** Request DTOs for the payables API. Money in paise. Mirrors api/app/domains/payables/schemas.py. */
import { IsBoolean, IsInt, IsOptional, IsString } from 'class-validator';

export class NewVendorDto {
  @IsString() name: string;
  @IsString() @IsOptional() gstin?: string | null;
  @IsString() @IsOptional() pan?: string | null;
  @IsBoolean() @IsOptional() msme_status = false;
  @IsInt() @IsOptional() payment_terms = 30;
  @IsString() @IsOptional() tds_section?: string | null;
  @IsString() @IsOptional() payee_type = 'company';
}

export class NewBillDto {
  @IsString() bill_number: string;
  @IsInt() vendor_id: number;
  @IsString() bill_date: string; // ISO
  @IsInt() subtotal: number; // paise (taxable)
  @IsInt() @IsOptional() gst_amount = 0;
  @IsInt() @IsOptional() igst_amount = 0;
  @IsInt() @IsOptional() cgst_amount = 0;
  @IsInt() @IsOptional() sgst_amount = 0;
  @IsInt() @IsOptional() po_id?: number | null;
  @IsBoolean() @IsOptional() itc_eligible = true;
  @IsString() @IsOptional() tds_category?: string | null; // e.g. "technical", "plant"
}
