/** Request DTOs for the vault API. Mirrors api/app/domains/vault/schemas.py. */
import { IsOptional, IsString } from 'class-validator';

export class IngestDocumentDto {
  @IsString() file_name: string;
  @IsString() content: string; // raw text or OCR text (image→text is the stubbed boundary)
  @IsString() @IsOptional() doc_type?: string | null;
  @IsString() @IsOptional() domain?: string | null;
  @IsString() @IsOptional() entity_id?: string | null;
  @IsString() @IsOptional() tags?: string | null;
  @IsString() @IsOptional() uploaded_by?: string | null;
}

export interface IngestResult {
  id: string;
  sha256: string;
  doc_type: string;
  retention_until: string | null;
  duplicate: boolean;
}
