/** Read/curate the org's CFO Profile (semantic hot layer). Auth-gated by the global guard. */
import { Body, Controller, Get, Post, Put, Query } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
import { IsString, MaxLength } from 'class-validator';

import { MemorySearchService } from './memory-search.service';
import { CFO_CHAR_LIMIT, MemoryService } from './memory.service';

class CfoDto {
  @IsString() @MaxLength(CFO_CHAR_LIMIT + 1) content: string; // hard cap enforced (reject) in the service
}
class AppendDto {
  @IsString() @MaxLength(500) line: string;
}

@ApiTags('memory')
@Controller('api/memory')
export class MemoryController {
  constructor(
    private readonly memory: MemoryService,
    private readonly search: MemorySearchService,
  ) {}

  /** Episodic recall over the sealed decision history (lexical BM25 / tsvector). */
  @Get('recall')
  recall(@Query('q') q: string, @Query('limit') limit?: string) {
    return this.search.recall(q ?? '', limit ? parseInt(limit, 10) : 10);
  }

  @Get()
  async profile() {
    const cfo = await this.memory.getCfo();
    return { cfo: cfo.content, used: cfo.used, limit: cfo.limit, profile: await this.memory.profileText() };
  }

  @Put('cfo')
  setCfo(@Body() body: CfoDto) {
    return this.memory.setCfo(body.content);
  }

  @Post('cfo/append')
  append(@Body() body: AppendDto) {
    return this.memory.appendCfo(body.line);
  }
}
