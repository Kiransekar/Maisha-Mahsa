/** Request DTOs for the revenue API. Money in paise. Mirrors api/app/domains/revenue/schemas.py. */
import { Type } from 'class-transformer';
import {
  IsArray,
  IsBoolean,
  IsInt,
  IsNumber,
  IsOptional,
  IsString,
  ValidateNested,
} from 'class-validator';

export class NewCustomerDto {
  @IsString() name: string;
  @IsString() @IsOptional() gstin?: string | null;
  @IsString() @IsOptional() pan?: string | null;
  @IsString() @IsOptional() state?: string | null;
  @IsInt() @IsOptional() payment_terms = 30;
  @IsBoolean() @IsOptional() tds_applicable = false;
  @IsNumber() @IsOptional() tds_rate = 0.0;
}

export class InvoiceLineDto {
  @IsString() description: string;
  @IsInt() @IsOptional() quantity = 1;
  @IsInt() rate: number; // paise per unit
  @IsString() @IsOptional() hsn_code?: string | null;
}

export class NewInvoiceDto {
  @IsString() invoice_number: string;
  @IsInt() customer_id: number;
  @IsString() invoice_date: string; // ISO
  @IsNumber() @IsOptional() gst_rate = 18.0;
  @IsArray() @ValidateNested({ each: true }) @Type(() => InvoiceLineDto) lines: InvoiceLineDto[] = [];
  @IsString() @IsOptional() irn?: string | null;
}
