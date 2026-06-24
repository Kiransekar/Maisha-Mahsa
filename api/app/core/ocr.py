"""OCR boundary — image bytes → text via Tesseract. Tesseract is a *system binary*, so this
module degrades cleanly: if the binary or the optional ``pytesseract``/``Pillow`` libraries are
absent it raises :class:`OcrUnavailable` (callers surface a 503), and the rest of the suite runs
untouched. Install with ``pip install -e api[ocr]`` plus the ``tesseract-ocr`` system package.

OCR only turns a scan into text; the resulting text flows into the existing, deterministic
parsers (expense ``parse_receipt``, vault ``ingest``) — OCR never produces a financial figure
that isn't then parsed and (for money) handled in exact paise downstream."""

from __future__ import annotations

import shutil
from io import BytesIO


class OcrUnavailable(RuntimeError):
    """Tesseract (binary or Python libs) is not installed in this environment."""


def tesseract_available() -> bool:
    """True only if both the ``tesseract`` binary and ``pytesseract``/``Pillow`` are importable."""
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def image_to_text(image_bytes: bytes) -> str:
    """Extract text from an image. Raises :class:`OcrUnavailable` if OCR isn't installed."""
    if shutil.which("tesseract") is None:
        raise OcrUnavailable("the 'tesseract-ocr' system binary is not installed")
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise OcrUnavailable(
            "OCR libraries missing — install with: pip install -e 'api[ocr]'"
        ) from exc

    with Image.open(BytesIO(image_bytes)) as img:
        return str(pytesseract.image_to_string(img)).strip()
