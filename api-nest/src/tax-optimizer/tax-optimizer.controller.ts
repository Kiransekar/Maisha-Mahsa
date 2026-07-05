/** The AI-CFO tax optimizer surface. Auth-gated by the global guard. */
import { Body, Controller, Get, Post, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
import { IsIn, IsString } from 'class-validator';

import { TaxOptimizerService } from './tax-optimizer.service';

class FeedbackDto {
  @IsString() playbook_id: string;
  @IsIn(['adopted', 'dismissed']) decision: string;
}

@ApiTags('optimize')
@Controller('api/optimize')
export class TaxOptimizerController {
  constructor(private readonly optimizer: TaxOptimizerService) {}

  @Get()
  optimize(@Query('as_of') asOf?: string) {
    return this.optimizer.optimize(asOf);
  }

  /** Record that the org adopted or dismissed a strategy (experiential memory). */
  @Post('feedback')
  feedback(@Body() body: FeedbackDto) {
    return this.optimizer.recordFeedback(body.playbook_id, body.decision);
  }
}
