/** Request/response DTOs for the equity API. Money in paise. Mirrors api/app/domains/equity/schemas.py. */
import { IsBoolean, IsInt, IsNumber, IsOptional, IsString } from 'class-validator';

export class NewShareholderDto {
  @IsString() name: string;
  @IsString() category: string; // founder/investor/esop/advisor
  @IsInt() @IsOptional() shares_held = 0;
  @IsInt() @IsOptional() investment_amount = 0; // paise
  @IsBoolean() @IsOptional() board_seat = false;
}

export class SafeConversionInputDto {
  @IsInt() investment: number; // paise
  @IsInt() @IsOptional() valuation_cap: number | null = null; // paise
  @IsNumber() @IsOptional() discount_rate = 0.0;
  @IsInt() round_price_per_share: number; // paise
  @IsInt() pre_round_shares: number;
}

export class SafeConversionResultDto {
  conversion_price_paise: number;
  shares_issued: number;
}
