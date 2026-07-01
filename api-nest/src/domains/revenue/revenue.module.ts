import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { Company } from '../../common/shared.entities';
import { RevenueController } from './revenue.controller';
import { CreditNote, Customer, Invoice, InvoiceItem } from './revenue.entities';
import { RevenueService } from './revenue.service';

@Module({
  imports: [TypeOrmModule.forFeature([Customer, Invoice, InvoiceItem, CreditNote, Company])],
  controllers: [RevenueController],
  providers: [RevenueService],
})
export class RevenueModule {}
