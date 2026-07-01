"""PaddleOCR sidecar — the best open-source OCR for Indian receipts/invoices/tables (PP-OCR).
Mirrors the Rust Mahsa sidecar pattern: a small stateless HTTP service the Nest app calls.
POST /ocr (multipart `file`) -> {"text": "<recognized lines>"}. GET /health -> readiness.

OCR only recognizes text; the deterministic parsers downstream extract amount/GSTIN/date in
exact paise, so this service never emits a financial figure that isn't re-parsed."""

from __future__ import annotations

import io
import os

# Disable oneDNN before Paddle imports: its new-IR executor hits an unimplemented op on some
# PP-OCR models on CPU (ConvertPirAttribute2RuntimeAttribute). The default kernels are fine.
os.environ.setdefault("FLAGS_use_mkldnn", "0")

import numpy as np
from fastapi import FastAPI, File, UploadFile
from paddleocr import PaddleOCR
from PIL import Image

app = FastAPI(title="Maisha OCR (PaddleOCR)")

# lang="en" covers Latin + digits (₹ amounts, GSTINs, dates); models cache on first run.
# enable_mkldnn=False avoids a oneDNN new-IR-executor op that is unimplemented for PP-OCRv6 on CPU.
_ocr = PaddleOCR(lang="en", enable_mkldnn=False)


def _extract(result) -> list[str]:
    """Flatten PaddleOCR output into text lines, robust across 2.x (nested lists) and 3.x
    (list of dict-like OCRResult with 'rec_texts')."""
    lines: list[str] = []
    for page in result or []:
        if isinstance(page, dict):  # 3.x
            for t in page.get("rec_texts", []) or []:
                if t:
                    lines.append(str(t))
            continue
        for line in page or []:  # 2.x: [box, (text, score)]
            try:
                text = line[1][0]
            except (IndexError, TypeError):
                continue
            if text:
                lines.append(str(text))
    return lines


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine": "paddleocr"}


@app.post("/ocr")
async def ocr(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    img = np.array(Image.open(io.BytesIO(data)).convert("RGB"))
    try:
        result = _ocr.predict(img)  # 3.x
    except AttributeError:
        result = _ocr.ocr(img)  # 2.x fallback
    return {"text": "\n".join(_extract(result))}
