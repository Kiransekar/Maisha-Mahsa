/** Read/curate the org's CFO Profile (semantic hot layer). Auth-gated by the global guard. */
import { Body, Controller, Get, Post, Put } from '@nestjs/common';
import { ApiTags } from '@nestjs/swagger';
import { IsString, MaxLength } from 'class-validator';

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
  constructor(private readonly memory: MemoryService) {}

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
