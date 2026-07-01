import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { VaultController } from './vault.controller';
import { Document } from './vault.entities';
import { VaultService } from './vault.service';

@Module({
  imports: [TypeOrmModule.forFeature([Document])],
  controllers: [VaultController],
  providers: [VaultService],
})
export class VaultModule {}
