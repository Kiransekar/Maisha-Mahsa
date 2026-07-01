# OCR sidecar (PaddleOCR)

Best-in-class open-source OCR for Indian receipts/invoices/tables (PP-OCRv6). A small stateless
HTTP service the Nest app calls when `MAISHA_OCR_PROVIDER=paddle` — the same sidecar pattern as the
Rust Mahsa engine. Tesseract stays the zero-infra default; this is the accuracy upgrade.

## Run

```bash
MAISHA_OCR_PROVIDER=paddle docker compose --profile ocr up -d --build
```

Heavy image (~paddle + models). Models cache in the container on first init (~60–70s to healthy).
`enable_mkldnn=False` avoids a oneDNN new-IR-executor op that is unimplemented for PP-OCRv6 on CPU.

## Endpoints

- `GET /health` → `{"status":"ok","engine":"paddleocr"}`
- `POST /ocr` (multipart `file`) → `{"text": "<recognized lines>"}`

## Smoke test (verified end-to-end)

A rendered Indian retail receipt → `POST /api/expense/parse-receipt/image` → PaddleOCR → the
deterministic parser (`expense.calc.parseReceipt`, exact paise):

```json
{
  "gstin": "27AAPFU0939F1ZV",
  "date": "15/05/2024",
  "amount_paise": 252402,      // ₹2,524.02 — the TOTAL (parser takes the max amount)
  "ocr_text": "SRI VENKATESWARA STORES\n... GSTIN: 27AAPFU0939F1ZV\n... TOTAL\nRs 2,524.02\n..."
}
```

OCR only recognizes text; the deterministic parser extracts amount/GSTIN/date in exact paise, so
the OCR engine never emits a financial figure that isn't re-parsed. The fixture receipt is at
`../docs/screenshots/09-ocr-receipt.png`.
