/** Prometheus scrape endpoint. Public (in the auth allowlist) so a scraper needs no session. */
import { Controller, Get, Header } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';

import { renderMetrics } from './metrics';

@ApiTags('observability')
@Controller('metrics')
export class MetricsController {
  @Get()
  @Header('Content-Type', 'text/plain; version=0.0.4')
  metrics(): string {
    return renderMetrics();
  }
}
