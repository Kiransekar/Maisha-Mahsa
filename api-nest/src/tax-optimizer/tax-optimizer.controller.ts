/** The AI-CFO tax optimizer surface. Auth-gated by the global guard. */
import { Controller, Get, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { TaxOptimizerService } from './tax-optimizer.service';

@ApiTags('optimize')
@Controller('api/optimize')
export class TaxOptimizerController {
  constructor(private readonly optimizer: TaxOptimizerService) {}

  @Get()
  optimize(@Query('as_of') asOf?: string) {
    return this.optimizer.optimize(asOf);
  }
}
