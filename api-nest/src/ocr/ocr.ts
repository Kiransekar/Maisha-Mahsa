/**
 * OCR boundary — image bytes → text via the Tesseract system binary. Port of api/app/core/ocr.py.
 * Tesseract is a system binary, so this degrades cleanly: if `tesseract` isn't on PATH it throws
 * OcrUnavailable (callers surface a 503) and the rest of the suite runs untouched. OCR only turns
 * a scan into text; the text flows into the existing deterministic parsers (expense parseReceipt),
 * so OCR never produces a financial figure that isn't then parsed and handled in exact paise.
 *
 * ponytail: spawn the `tesseract` CLI (no dep) instead of a WASM tesseract — mirrors the Python
 * shutil.which degradation exactly. Upgrade to tesseract.js only if a binary-less deploy needs OCR.
 */
import { execFile } from 'child_process';
import { mkdtemp, rm, writeFile } from 'fs/promises';
import { tmpdir } from 'os';
import { join } from 'path';

export class OcrUnavailable extends Error {}

function which(bin: string): boolean {
  const paths = (process.env.PATH ?? '').split(':');
  const { existsSync } = require('fs');
  return paths.some((p) => p && existsSync(join(p, bin)));
}

export function tesseractAvailable(): boolean {
  return which('tesseract');
}

/** Extract text from an image. Throws OcrUnavailable if the tesseract binary is not installed. */
export async function imageToText(imageBytes: Buffer): Promise<string> {
  if (!tesseractAvailable()) {
    throw new OcrUnavailable("the 'tesseract-ocr' system binary is not installed");
  }
  const dir = await mkdtemp(join(tmpdir(), 'maisha-ocr-'));
  const imgPath = join(dir, 'in');
  try {
    await writeFile(imgPath, imageBytes);
    // `tesseract <img> stdout` prints recognized text to stdout.
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
