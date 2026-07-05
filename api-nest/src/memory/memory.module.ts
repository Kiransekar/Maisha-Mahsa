/** Semantic hot-layer memory (CFO Profile). Global so the drafting loop + tax optimizer can inject it. */
import { Global, Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { Company } from '../common/shared.entities';
import { MemoryController } from './memory.controller';
import { MemoryService } from './memory.service';
import { OrgMemory } from './org-memory.entities';

@Global()
@Module({
  imports: [TypeOrmModule.forFeature([OrgMemory, Company])],
  controllers: [MemoryController],
  providers: [MemoryService],
  exports: [MemoryService],
})
export class MemoryModule {}
