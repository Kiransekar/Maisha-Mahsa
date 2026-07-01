import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { ExpenseController } from './expense.controller';
import { ExpenseClaim } from './expense.entities';
import { ExpenseService } from './expense.service';

@Module({
  imports: [TypeOrmModule.forFeature([ExpenseClaim])],
  controllers: [ExpenseController],
  providers: [ExpenseService],
})
export class ExpenseModule {}
