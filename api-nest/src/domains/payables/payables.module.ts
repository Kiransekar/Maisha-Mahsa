import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { PayablesController } from './payables.controller';
import { Bill, PurchaseOrder, Vendor } from './payables.entities';
import { PayablesService } from './payables.service';

@Module({
  imports: [TypeOrmModule.forFeature([Vendor, PurchaseOrder, Bill])],
  controllers: [PayablesController],
  providers: [PayablesService],
})
export class PayablesModule {}
