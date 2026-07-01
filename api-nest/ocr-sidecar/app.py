"""PaddleOCR sidecar — the best open-source OCR for Indian receipts/invoices/tables (PP-OCR).
Mirrors the Rust Mahsa sidecar pattern: a small stateless HTTP service the Nest app calls.
POST /ocr (multipart `file`) -> {"text": "<recognized lines>"}. GET /health -> readiness.

OCR only recognizes text; the deterministic parsers downstream extract amount/GSTIN/date in
exact paise, so this service never emits a financial figure that isn't re-parsed."""

from __future__ import annotations

import io

import numpy as np
from fastapi import FastAPI, File, UploadFile
from paddleocr import PaddleOCR
from PIL import Image

app = FastAPI(title="Maisha OCR (PaddleOCR)")

# lang="en" covers Latin script + digits (₹ amounts, GSTINs, dates). Angle classification on so
# rotated phone photos of receipts still read. Models download once on first run, then cache.
_ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "engine": "paddleocr"}


@app.post("/ocr")
async def ocr(file: UploadFile = File(...)) -> dict:
    data = await file.read()
    img = np.array(Image.open(io.BytesIO(data)).convert("RGB"))
    result = _ocr.ocr(img, cls=True)

    # PaddleOCR returns nested [page][line] = [box, (text, score)]; be defensive across versions.
    lines: list[str] = []
    for page in result or []:
        for line in page or []:
            try:
                text = line[1][0]
            except (IndexError, TypeError):
                continue
            if text:
                lines.append(str(text))
    return {"text": "\n".join(lines)}
