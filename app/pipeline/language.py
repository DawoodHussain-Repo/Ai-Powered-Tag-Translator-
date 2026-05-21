from __future__ import annotations

import re
from typing import NamedTuple

import pytesseract
from langdetect import detect_langs
from langdetect.lang_detect_exception import LangDetectException
from PIL import Image

from app.config import Settings
from app.models.schemas import TextBlock


class LanguageResult(NamedTuple):
    """Result of the two-step language detection process.

    Attributes:
        language_code: ISO 639-1 code (e.g. ``"es"``, ``"en"``) or ``"unknown"``.
        is_english: ``True`` only when OSD confirms Latin script AND langdetect
                    detects English with sufficient confidence.
    """
    language_code: str
    is_english: bool


def _parse_osd_script(osd_output: str) -> str:
    """Extract the script name from pytesseract OSD output.

    The OSD output contains lines like ``Script: Latin`` or ``Script: Cyrillic``.
    Returns the script name as a string, or ``"unknown"`` if not found.
    """
    match = re.search(r"Script:\s*(\S+)", osd_output)
    if match:
        return match.group(1)
    return "unknown"


def _detect_with_langdetect(
    text: str,
    min_confidence: float,
) -> tuple[str, bool]:
    """Run langdetect on the text and return (language_code, is_english).

    Returns ``("unknown", False)`` if langdetect raises or confidence
    is below the threshold (fail open).
    """
    try:
        results = detect_langs(text)
    except LangDetectException:
        return ("unknown", False)
    except Exception:
        return ("unknown", False)

    if not results:
        return ("unknown", False)

    top = results[0]
    lang_code = str(top.lang)
    confidence = float(top.prob)

    if confidence < min_confidence:
        # Below confidence threshold — fail open, proceed to translation
        return ("unknown", False)

    return (lang_code, lang_code == "en")


def detect_language(
    preprocessed_image: Image.Image,
    blocks: list[TextBlock],
    settings: Settings,
) -> LanguageResult:
    """Detect the source language using OSD script detection + langdetect.

    This is the main entry point for Node 4 (LanguageDetector).

    **Step 1**: Run ``pytesseract.image_to_osd()`` on the preprocessed image
    to determine the script family (Latin, Cyrillic, Arabic, Han, etc.).
    If the script is non-Latin, proceed directly to translation — no further
    detection is needed.

    **Step 2** (Latin script only): Run ``langdetect.detect_langs()`` on
    the concatenated OCR text from Node 3.  If the top result is ``"en"``
    with confidence ≥ ``LANGDETECT_MIN_CONFIDENCE``, trigger the early return
    (``is_english=True``).  Otherwise proceed to translation.

    **Failure handling**: All errors fail open — any detection error
    proceeds to Node 5 (TextTranslator), never blocks the pipeline.

    Args:
        preprocessed_image: The OCR-optimised image from Node 2.
        blocks: Text blocks extracted by Node 3 (OCRExtractor).
        settings: Application settings containing LANGDETECT_MIN_CONFIDENCE.

    Returns:
        A ``LanguageResult`` with ``language_code`` and ``is_english``.
    """
    # Step 1: OSD script detection
    try:
        osd_output = pytesseract.image_to_osd(preprocessed_image)
        script = _parse_osd_script(osd_output)
    except Exception:
        # OSD failed — fail open, proceed to translation
        return LanguageResult(language_code="unknown", is_english=False)

    # Non-Latin script → proceed directly to translation
    if script != "Latin":
        return LanguageResult(language_code="unknown", is_english=False)

    # Step 2: langdetect on concatenated OCR text (Latin script only)
    combined_text = " ".join(block.text for block in blocks).strip()
    if not combined_text:
        return LanguageResult(language_code="unknown", is_english=False)

    lang_code, is_en = _detect_with_langdetect(
        combined_text,
        min_confidence=settings.LANGDETECT_MIN_CONFIDENCE,
    )
    return LanguageResult(language_code=lang_code, is_english=is_en)
