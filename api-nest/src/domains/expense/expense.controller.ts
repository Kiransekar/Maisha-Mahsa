/** Expense routes (thin — delegate to the service and the loop). Mirrors api/app/domains/expense/router.py. */
import {
  BadRequestException,
  Body,
  Controller,
  Get,
  HttpException,
  HttpStatus,
  Param,
  Post,
  Query,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { ApiTags } from '@nestjs/swagger';

import { LoopService } from '../../core/loop.service';
import { NewClaimDto, ReceiptTextDto } from './expense.dto';
import { ExpenseService } from './expense.service';

@ApiTags('expense')
@Controller('api/expense')
export class ExpenseController {
  constructor(
    private readonly service: ExpenseService,
    private readonly loop: LoopService,
  ) {}

  @Post('claims')
  submitClaim(@Body() body: NewClaimDto) {
    return this.service.submitClaim({
      claim_date: body.claim_date,
      expense_date: body.expense_date,
      category: body.category,
      amount: body.amount,
      gst_amount: body.gst_amount,
      employee_id: body.employee_id ?? null,
      vendor_name: body.vendor_name ?? null,
      description: body.description ?? null,
    });
  }

  @Post('claims/:claim_id/approve')
  async approve(@Param('claim_id') claimId: string, @Query('approver') approver: string) {
    try {
      await this.service.approveClaim(Number(claimId), {
        approver,
        approved_date: new Date().toISOString().slice(0, 10),
      });
    } catch (exc) {
      throw new HttpException((exc as Error).message, HttpStatus.NOT_FOUND);
    }
    return { status: 'approved' };
  }

  @Get('analytics')
  analytics() {
    return this.service.categorySpend();
  }

  @Post('parse-receipt')
  parseReceipt(@Body() body: ReceiptTextDto) {
    return this.service.parseReceipt(body.ocr_text);
  }

  /** Upload a receipt image (multipart `file`); OCR it, then parse. 503 if OCR is unavailable. */
  @Post('parse-receipt/image')
  @UseInterceptors(
    FileInterceptor('file', {
      limits: { fileSize: 5 * 1024 * 1024, files: 1 },
      fileFilter: (_req, f, cb) => cb(null, f.mimetype.startsWith('image/')),
    }),
  )
  parseReceiptImage(@UploadedFile() file: Express.Multer.File) {
    if (!file) throw new BadRequestException('multipart field `file` (an image) is required');
    return this.service.parseReceiptImage(file.buffer);
  }

  /** Fold the expense snapshot through Mahsa and seal it into the audit chain (the Golden Rule). */
  @Post('fold')
  async fold(@Query('as_of') asOf?: string) {
    const outcome = await this.loop.run({
      service: this.service,
      timestamp: new Date().toISOString(),
      asOf,
      action: 'expense.fold',
    });
    return {
      snapshot: outcome.snapshot,
      validation: outcome.fold.validation,
      shape: outcome.fold.shape,
      audit_hash: outcome.auditHash,
    };
  }
}
