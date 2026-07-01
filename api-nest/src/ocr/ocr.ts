/**
 * OCR boundary — image bytes → text. Pluggable provider so the suite can use the best engine
 * available while degrading cleanly. OCR only turns a scan into text; the text flows into the
 * existing deterministic parsers (expense parseReceipt), so OCR never produces a financial figure
 * that isn't then parsed and handled in exact paise.
 *
 * Providers (MAISHA_OCR_PROVIDER):
 *  - `tesseract` (default) — spawns the local `tesseract` CLI. Zero infra; fastest on clean docs.
 *  - `paddle` — PaddleOCR sidecar over HTTP (MAISHA_OCR_URL). Best accuracy on Indian receipts,
 *    invoices, and tables (see ocr-sidecar/). Falls back nowhere: if configured but unreachable it
 *    surfaces OcrUnavailable (503), never a silent wrong read.
 */
import { execFile } from 'child_process';
import { existsSync } from 'fs';
import { mkdtemp, rm, writeFile } from 'fs/promises';
import { tmpdir } from 'os';
import { join } from 'path';

export class OcrUnavailable extends Error {}

export interface OcrProvider {
  readonly name: string;
  available(): Promise<boolean>;
  imageToText(imageBytes: Buffer): Promise<string>;
}

// ---- Tesseract (local CLI) ------------------------------------------------------------

function which(bin: string): boolean {
  return (process.env.PATH ?? '').split(':').some((p) => p && existsSync(join(p, bin)));
}

export function tesseractAvailable(): boolean {
  return which('tesseract');
}

class TesseractProvider implements OcrProvider {
  readonly name = 'tesseract';
  async available(): Promise<boolean> {
    return tesseractAvailable();
  }
  async imageToText(imageBytes: Buffer): Promise<string> {
    if (!tesseractAvailable()) throw new OcrUnavailable("the 'tesseract-ocr' system binary is not installed");
    const dir = await mkdtemp(join(tmpdir(), 'maisha-ocr-'));
    const imgPath = join(dir, 'in');
    try {
      await writeFile(imgPath, imageBytes);
      const text: string = await new Promise((resolve, reject) => {
        execFile('tesseract', [imgPath, 'stdout'], { timeout: 30_000 }, (err, stdout) => {
          if (err) reject(new OcrUnavailable(`tesseract failed: ${err.message}`));
          else resolve(stdout);
        });
      });
      return text.trim();
    } finally {
      await rm(dir, { recursive: true, force: true }).catch(() => undefined);
    }
  }
}

// ---- PaddleOCR (sidecar over HTTP) ----------------------------------------------------

class PaddleOcrProvider implements OcrProvider {
  readonly name = 'paddle';
  private readonly url: string;
  private readonly timeoutMs: number;
  constructor() {
    this.url = (process.env.MAISHA_OCR_URL ?? 'http://127.0.0.1:8090').replace(/\/+$/, '');
    this.timeoutMs = Number(process.env.MAISHA_OCR_TIMEOUT_MS ?? 30_000);
  }
  async available(): Promise<boolean> {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 3000);
      const r = await fetch(`${this.url}/health`, { signal: ctrl.signal });
      clearTimeout(t);
      return r.ok;
    } catch {
      return false;
    }
  }
  async imageToText(imageBytes: Buffer): Promise<string> {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const form = new FormData();
      form.append('file', new Blob([new Uint8Array(imageBytes)]), 'receipt');
      const resp = await fetch(`${this.url}/ocr`, { method: 'POST', body: form, signal: ctrl.signal });
      if (!resp.ok) throw new OcrUnavailable(`PaddleOCR sidecar failed: HTTP ${resp.status}`);
      const body = (await resp.json()) as { text?: string };
      return (body.text ?? '').trim();
    } catch (e) {
      if (e instanceof OcrUnavailable) throw e;
      throw new OcrUnavailable(`PaddleOCR sidecar unreachable: ${(e as Error).message}`);
    } finally {
      clearTimeout(t);
    }
  }
}

// ---- selection ------------------------------------------------------------------------

let _provider: OcrProvider | null = null;
export function ocrProvider(): OcrProvider {
  if (_provider) return _provider;
  _provider = (process.env.MAISHA_OCR_PROVIDER ?? 'tesseract') === 'paddle' ? new PaddleOcrProvider() : new TesseractProvider();
  return _provider;
}

/** Extract text via the configured provider. Throws OcrUnavailable if OCR isn't usable. */
export function imageToText(imageBytes: Buffer): Promise<string> {
  return ocrProvider().imageToText(imageBytes);
}
