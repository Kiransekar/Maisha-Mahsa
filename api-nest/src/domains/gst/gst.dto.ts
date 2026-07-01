/** Request DTOs for the GST API. Money in paise. Mirrors api/app/domains/gst/schemas.py. */
import { Type } from 'class-transformer';
import {
  IsArray,
  IsBoolean,
  IsInt,
  IsObject,
  IsOptional,
  IsString,
  ValidateNested,
} from 'class-validator';

export class TaxHeadsDto {
  @IsInt() @IsOptional() igst = 0;
  @IsInt() @IsOptional() cgst = 0;
  @IsInt() @IsOptional() sgst = 0;
}

export class Gstr3bInputDto {
  @IsString() filing_period: string; // "YYYY-MM"
  @IsString() due_date: string; // ISO
  @IsString() @IsOptional() filed_date?: string | null;
  @IsBoolean() @IsOptional() is_nil = false;

  @IsObject() @ValidateNested() @Type(() => TaxHeadsDto) output: TaxHeadsDto;
  @IsObject() @ValidateNested() @Type(() => TaxHeadsDto) itc_available: TaxHeadsDto;
}

export class SupplyLineDto {
  @IsString() invoice_no: string;
  @IsInt() taxable: number;
  @IsInt() @IsOptional() igst = 0;
  @IsInt() @IsOptional() cgst = 0;
  @IsInt() @IsOptional() sgst = 0;
  @IsString() @IsOptional() hsn?: string | null;
  @IsString() @IsOptional() gstin?: string | null;
  @IsInt() @IsOptional() qty = 0;
}

export class Gstr1InputDto {
  @IsString() filing_period: string;
  @IsArray() @ValidateNested({ each: true }) @Type(() => SupplyLineDto) lines: SupplyLineDto[] = [];
}
