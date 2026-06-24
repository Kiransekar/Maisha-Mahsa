"""OCR boundary — graceful degradation when Tesseract isn't installed, and the real path when
it is (skipped otherwise). CI runs without the binary, so the degradation path is what's tested."""

from __future__ import annotations

import pytest

from app.core import ocr
from app.domains.expense.service import ExpenseService
from app.domains.vault.service import VaultService


def test_availability_is_bool() -> None:
    assert isinstance(ocr.tesseract_available(), bool)


@pytest.mark.skipif(ocr.tesseract_available(), reason="tesseract installed — degradation N/A")
def test_image_to_text_raises_when_unavailable() -> None:
    with pytest.raises(ocr.OcrUnavailable):
        ocr.image_to_text(b"\x89PNG not-a-real-image")


@pytest.mark.skipif(ocr.tesseract_available(), reason="tesseract installed")
def test_expense_ocr_capture_degrades() -> None:
    with pytest.raises(ocr.OcrUnavailable):
        ExpenseService().ocr_capture(b"fake-image-bytes")


@pytest.mark.skipif(ocr.tesseract_available(), reason="tesseract installed")
def test_vault_ingest_image_degrades(session) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ocr.OcrUnavailable):
        VaultService().ingest_image(
            session, file_name="scan.png", image_bytes=b"fake", upload_date="2026-05-10"
        )


@pytest.mark.skipif(not ocr.tesseract_available(), reason="tesseract not installed")
def test_real_ocr_roundtrip_when_available() -> None:
    # Only runs where Tesseract + libs are present; a blank image yields a string (often empty).
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (60, 30), "white").save(buf, format="PNG")
    assert isinstance(ocr.image_to_text(buf.getvalue()), str)
