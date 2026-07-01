import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { PayrollController } from './payroll.controller';
import { Employee, EsopGrant, PayrollEntry, PayrollRun, SalaryStructure } from './payroll.entities';
import { PayrollService } from './payroll.service';

@Module({
  imports: [
    TypeOrmModule.forFeature([Employee, SalaryStructure, PayrollRun, PayrollEntry, EsopGrant]),
  ],
  controllers: [PayrollController],
  providers: [PayrollService],
})
export class PayrollModule {}
