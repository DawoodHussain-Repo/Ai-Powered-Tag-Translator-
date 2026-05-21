from __future__ import annotations

from typing import Literal

import pytesseract
from langdetect import detect
from PIL import Image


def verify_output(image: Image.Image) -> Literal["pass", "fail"]:
    """Run re-OCR and language detection on the composited image.

    This is the main entry point for Node 6.

    Uses ``pytesseract.image_to_string()`` to extract text from the
    composited image, then runs ``langdetect.detect()`` on the result.

    Returns:
        ``"pass"`` if the detected language is English (``"en"``).
        ``"fail"`` if the language is not English or detection fails.
    """
    try:
        extracted_text = pytesseract.image_to_string(image).strip()
    except Exception:
        return "fail"

    if not extracted_text:
        # No text detected at all — cannot verify, treat as failure
        return "fail"

    try:
        detected_lang = detect(extracted_text.lower())
    except Exception:
        return "fail"

    if detected_lang == "en":
        return "pass"

    return "fail"
