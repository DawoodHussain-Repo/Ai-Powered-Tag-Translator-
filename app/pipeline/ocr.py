from __future__ import annotations

import pytesseract
from PIL import Image
from pytesseract import Output

from app.config import Settings
from app.exceptions import OCRError
from app.models.schemas import TextBlock


def _is_noise(text: str) -> bool:
    """Return True if the text is a single non-alphanumeric character.

    These are typically OCR artifacts like bullets (•), pipes (|),
    dashes (-), or other decorative characters that should not be
    treated as translatable text blocks.
    """
    return len(text) == 1 and not text.isalnum()


def _group_words_into_blocks(
    ocr_data: dict,
    min_confidence: int,
    min_bbox_area: int = 100,
) -> list[TextBlock]:
    """Group individual words from Tesseract output into block-level text chunks.

    Words are grouped by their ``block_num``, ``par_num``, and ``line_num``
    from the Tesseract output.  Each group becomes one ``TextBlock`` whose
    bounding box is the union rectangle of all its constituent words.

    Words with confidence below ``min_confidence`` are discarded.
    After grouping, blocks are filtered to remove noise:
    - Single non-alphanumeric character blocks
    - Blocks with bbox area (w × h) below ``min_bbox_area``
    """
    groups: dict[tuple[int, int, int], list[dict]] = {}

    n_items = len(ocr_data["text"])
    for i in range(n_items):
        text = ocr_data["text"][i].strip()
        if not text:
            continue

        try:
            conf = int(ocr_data["conf"][i])
        except (ValueError, TypeError):
            continue

        if conf < min_confidence:
            continue

        key = (
            int(ocr_data["block_num"][i]),
            int(ocr_data["par_num"][i]),
            int(ocr_data["line_num"][i]),
        )
        word_info = {
            "text": text,
            "left": int(ocr_data["left"][i]),
            "top": int(ocr_data["top"][i]),
            "width": int(ocr_data["width"][i]),
            "height": int(ocr_data["height"][i]),
            "conf": conf,
        }
        groups.setdefault(key, []).append(word_info)

    blocks: list[TextBlock] = []
    for _key, words in sorted(groups.items()):
        combined_text = " ".join(w["text"] for w in words)
        x_min = min(w["left"] for w in words)
        y_min = min(w["top"] for w in words)
        x_max = max(w["left"] + w["width"] for w in words)
        y_max = max(w["top"] + w["height"] for w in words)
        avg_conf = sum(w["conf"] for w in words) / len(words)

        w = x_max - x_min
        h = y_max - y_min

        # Noise filter: skip single non-alphanumeric characters
        if _is_noise(combined_text):
            continue

        # Noise filter: skip blocks with bounding box area below threshold
        if w * h < min_bbox_area:
            continue

        blocks.append(
            TextBlock(
                text=combined_text,
                bbox=(x_min, y_min, w, h),
                confidence=round(avg_conf, 2),
            )
        )

    return blocks


def extract_text(image: Image.Image, settings: Settings) -> list[TextBlock]:
    """Run OCR on the image and return grouped text blocks.

    This is the main entry point for Node 3.  It calls Tesseract via
    ``pytesseract.image_to_data()`` and groups the output into block-level
    ``TextBlock`` objects filtered by the configured confidence threshold
    and noise filters (single non-alphanumeric chars, small bbox area).

    Returns an empty list if no text is found (caller handles the early-return).
    Raises ``OCRError`` if Tesseract fails unexpectedly.
    """
    try:
        ocr_data = pytesseract.image_to_data(image, output_type=Output.DICT)
    except Exception as exc:
        raise OCRError(f"Tesseract OCR failed: {exc}") from exc

    return _group_words_into_blocks(
        ocr_data,
        settings.MIN_OCR_CONFIDENCE,
        min_bbox_area=settings.MIN_BBOX_AREA,
    )
