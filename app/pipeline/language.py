from __future__ import annotations

from langdetect import detect
from langdetect.lang_detect_exception import LangDetectException

from app.models.schemas import TextBlock


def detect_language(blocks: list[TextBlock]) -> str:
    """Detect the source language of the extracted text blocks.

    This is the main entry point for Node 3.  It concatenates all block
    texts and runs ``langdetect.detect()`` to determine the ISO 639-1
    language code.

    Returns:
        An ISO 639-1 language code (e.g. ``"es"``, ``"en"``, ``"zh-cn"``).
        Returns ``"unknown"`` if detection fails or is indeterminate.
    """
    combined = " ".join(block.text for block in blocks).strip().lower()
    if not combined:
        return "unknown"

    try:
        return detect(combined)
    except Exception:
        return "unknown"


def is_english(language_code: str) -> bool:
    """Check whether the detected language code indicates English.

    Returns ``True`` if the code is ``"en"`` — the caller should
    trigger the early-return path (return original image, no Gemini call).
    """
    return language_code == "en"
