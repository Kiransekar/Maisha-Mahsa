/**
 * HTTP client to the Mahsa (Rust) sidecar — the ONLY path to a validated result.
 * Maisha never decides Green/Yellow/Red itself. Mirrors api/app/core/mahsa_client.py.
 * We fail loud (MahsaError) rather than fabricate a verdict when the sidecar is down.
 */
import { Injectable } from '@nestjs/common';

export interface Banner {
  severity: string;
  text: string;
  citation: string;
  action: string;
}

export interface ResponseShape {
  status: string;
  color: string;
  layout: string;
  requires_approval: boolean;
  banners: Banner[];
  global_score: number;
  domain_score?: number | null;
}

export interface TriggeredRule {
  id: string;
  domain: string;
  severity: string;
  description: string;
  statute: string;
  section: string;
  action: string;
}

export interface Validation {
  status: string;
  triggered: TriggeredRule[];
}

export interface FoldResult {
  global_intent: number[];
  global_dims: string[];
  domain?: string | null;
  domain_intent?: number[] | null;
  validation: Validation;
  shape: ResponseShape;
  rules_version: string;
}

export class MahsaError extends Error {}

@Injectable()
export class MahsaService {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor() {
    this.baseUrl = (process.env.MAISHA_MAHSA_URL ?? 'http://127.0.0.1:8088').replace(/\/+$/, '');
    this.timeoutMs = Number(process.env.MAISHA_MAHSA_TIMEOUT_MS ?? 5000);
  }

  private async post(path: string, body: unknown): Promise<any> {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const resp = await fetch(`${this.baseUrl}${path}`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      if (!resp.ok) throw new MahsaError(`Mahsa ${path} failed: HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      if (e instanceof MahsaError) throw e;
      throw new MahsaError(`Mahsa ${path} failed: ${(e as Error).message}`);
    } finally {
      clearTimeout(t);
    }
  }

  async health(): Promise<any> {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const resp = await fetch(`${this.baseUrl}/health`, { signal: ctrl.signal });
      if (!resp.ok) throw new MahsaError(`Mahsa health failed: HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      if (e instanceof MahsaError) throw e;
      throw new MahsaError(`Mahsa health check failed: ${(e as Error).message}`);
    } finally {
      clearTimeout(t);
    }
  }

  async fold(
    snapshot: Record<string, any>,
    opts: { domain?: string; query?: string; rulesVersion?: string } = {},
  ): Promise<FoldResult> {
    const payload: Record<string, any> = { snapshot };
    if (opts.domain != null) payload.domain = opts.domain;
    if (opts.query != null) payload.query = opts.query;
    if (opts.rulesVersion != null) payload.rules_version = opts.rulesVersion;
    return (await this.post('/fold', payload)) as FoldResult;
  }
}
