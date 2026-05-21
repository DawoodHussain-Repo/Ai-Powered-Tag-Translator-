from __future__ import annotations

import re
from typing import Literal

import pytesseract
from PIL import Image


def verify_output(image: Image.Image) -> Literal["pass", "fail"]:
    """Run re-OCR and heuristic presence check on the composited image.

    This is the main entry point for Node 7 (OutputVerifier).

    Uses ``pytesseract.image_to_string()`` to extract text from the
    composited image, then checks that the result is non-empty and
    contains at least one alphabetic token of length > 2.

    This is a heuristic presence check — not a language classification.
    It verifies that *some* readable text was rendered, without attempting
    to determine whether it is English.

    Returns:
        ``"pass"`` if the heuristic check passes.
        ``"fail"`` if the text is empty, unreadable, or contains no
        alphabetic tokens of length > 2.
    """
    try:
        extracted_text = pytesseract.image_to_string(image).strip()
    except Exception:
        return "fail"

    if not extracted_text:
        return "fail"

    # Tokenise on whitespace and check for at least one alphabetic token > 2 chars
    tokens = re.findall(r"[A-Za-z]+", extracted_text)
    has_meaningful_token = any(len(t) > 2 for t in tokens)

    if has_meaningful_token:
        return "pass"

    return "fail"
