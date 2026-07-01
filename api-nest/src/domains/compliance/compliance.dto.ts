/** Request DTOs for the compliance API. Mirrors api/app/domains/compliance/schemas.py. */
import { IsOptional, IsString } from 'class-validator';

export class NewDeadlineDto {
  @IsString() domain: string; // roc/gst/tds/pf/esi/pt
  @IsString() form_name: string;
  @IsString() due_date: string; // ISO
  @IsString() @IsOptional() filing_period?: string | null;
}

export class MarkFiledDto {
  @IsString() filed_date: string;
  @IsString() @IsOptional() acknowledgement?: string | null;
}
