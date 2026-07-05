/** Global spine: Mahsa client + audit chain + fold loop + optional LLM drafting. */
import { Global, Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';

import { AuditLog, LlmTrace } from '../common/shared.entities';
import { AuditService } from '../audit/audit.service';
import { AuditController } from '../audit/audit.controller';
import { buildClient } from '../llm/client';
import { MaishaGenerator } from '../llm/maisha';
import { TraceService } from '../llm/trace.service';
import { MahsaService } from '../mahsa/mahsa.service';
import { CLAIM_PRODUCER, LoopService } from './loop.service';

// Env-gated drafting generator. `off` (default) → null, so the loop stays deterministic.
const claimProducer = {
  provide: CLAIM_PRODUCER,
  useFactory: () => {
    const provider = process.env.MAISHA_LLM_PROVIDER ?? 'off';
    if (provider === 'off') return null;
    const model =
      provider === 'claude'
        ? (process.env.MAISHA_CLAUDE_MODEL ?? 'claude-opus-4-8')
        : (process.env.MAISHA_OLLAMA_MODEL ?? 'qwen3:14b');
    // Cloud (Claude) redacts PII by default (opt-out); local Ollama opts in. Never send unredacted
    // PAN/Aadhaar/GSTIN to a third party unless explicitly disabled.
    const redactPii = provider === 'claude' ? process.env.MAISHA_LLM_REDACT_PII !== 'false' : process.env.MAISHA_LLM_REDACT_PII === 'true';
    return new MaishaGenerator(buildClient(), `${provider}:${model}`, redactPii);
  },
};

@Global()
@Module({
  imports: [TypeOrmModule.forFeature([AuditLog, LlmTrace])],
  controllers: [AuditController],
  providers: [MahsaService, AuditService, TraceService, claimProducer, LoopService],
  exports: [MahsaService, AuditService, TraceService, LoopService],
})
export class CoreModule {}
