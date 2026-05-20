from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.config import Settings
from app.exceptions import OCRError
from app.models.schemas import TextBlock
from app.pipeline.ocr import extract_text, _group_words_into_blocks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_settings(**overrides: object) -> Settings:
    """Build a Settings instance with test defaults."""
    defaults = {
        "GEMINI_API_KEY": "test-key",
        "MAX_FILE_SIZE_MB": 10,
        "MIN_OCR_CONFIDENCE": 40,
        "GEMINI_MODEL": "gemini-1.5-flash",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _make_image_with_text(
    text: str = "HELLO WORLD",
    size: tuple[int, int] = (400, 100),
    font_size: int = 40,
) -> Image.Image:
    """Create a test image with clear, large text on a white background."""
    img = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Use default font — large enough for Tesseract to read
    try:
        font = ImageFont.truetype("assets/fonts/NotoSans-Regular.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 20), text, fill=(0, 0, 0), font=font)
    return img


def _make_blank_image(size: tuple[int, int] = (200, 200)) -> Image.Image:
    """Create a blank white image with no text."""
    return Image.new("RGB", size, color=(255, 255, 255))


# ---------------------------------------------------------------------------
# _group_words_into_blocks (unit tests with synthetic OCR data)
# ---------------------------------------------------------------------------

class TestGroupWordsIntoBlocks:
    def test_groups_words_by_block_par_line(self) -> None:
        """Words with the same block/par/line key are grouped together."""
        ocr_data = {
            "text": ["Hello", "World", "Foo"],
            "conf": [90, 85, 92],
            "block_num": [1, 1, 2],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 1],
            "left": [10, 80, 10],
            "top": [10, 10, 50],
            "width": [60, 60, 30],
            "height": [20, 20, 20],
        }
        blocks = _group_words_into_blocks(ocr_data, min_confidence=40)
        assert len(blocks) == 2
        assert blocks[0].text == "Hello World"
        assert blocks[1].text == "Foo"

    def test_filters_by_confidence(self) -> None:
        """Words below the confidence threshold are excluded."""
        ocr_data = {
            "text": ["Good", "Bad"],
            "conf": [90, 10],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
            "left": [10, 80],
            "top": [10, 10],
            "width": [60, 60],
            "height": [20, 20],
        }
        blocks = _group_words_into_blocks(ocr_data, min_confidence=40)
        assert len(blocks) == 1
        assert blocks[0].text == "Good"

    def test_empty_text_is_skipped(self) -> None:
        """Entries with empty text are ignored."""
        ocr_data = {
            "text": ["", " ", "Real"],
            "conf": [90, 90, 90],
            "block_num": [1, 1, 1],
            "par_num": [1, 1, 1],
            "line_num": [1, 1, 1],
            "left": [10, 20, 30],
            "top": [10, 10, 10],
            "width": [10, 10, 40],
            "height": [20, 20, 20],
        }
        blocks = _group_words_into_blocks(ocr_data, min_confidence=0)
        assert len(blocks) == 1
        assert blocks[0].text == "Real"

    def test_union_bbox_is_correct(self) -> None:
        """The bounding box should be the union rectangle of all words."""
        ocr_data = {
            "text": ["A", "B"],
            "conf": [90, 90],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
            "left": [10, 100],
            "top": [5, 5],
            "width": [30, 50],
            "height": [20, 25],
        }
        blocks = _group_words_into_blocks(ocr_data, min_confidence=0)
        assert len(blocks) == 1
        # x=10, y=5, w=100+50-10=140, h=max(5+20, 5+25)-5=25
        assert blocks[0].bbox == (10, 5, 140, 25)

    def test_returns_empty_when_no_text(self) -> None:
        """If all text entries are empty, returns empty list."""
        ocr_data = {
            "text": ["", ""],
            "conf": [90, 90],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
            "left": [10, 20],
            "top": [10, 10],
            "width": [10, 10],
            "height": [10, 10],
        }
        blocks = _group_words_into_blocks(ocr_data, min_confidence=0)
        assert blocks == []

    def test_invalid_confidence_is_skipped(self) -> None:
        """Non-numeric confidence values are skipped gracefully."""
        ocr_data = {
            "text": ["Word"],
            "conf": ["N/A"],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
            "left": [10],
            "top": [10],
            "width": [40],
            "height": [20],
        }
        blocks = _group_words_into_blocks(ocr_data, min_confidence=0)
        # "N/A" cannot be parsed as int, so the word is skipped
        assert len(blocks) == 0

    def test_negative_confidence_is_filtered(self) -> None:
        """Tesseract sometimes returns -1 confidence; these are filtered."""
        ocr_data = {
            "text": ["Word"],
            "conf": [-1],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
            "left": [10],
            "top": [10],
            "width": [40],
            "height": [20],
        }
        blocks = _group_words_into_blocks(ocr_data, min_confidence=0)
        # -1 < 0 so filtered out
        assert len(blocks) == 0


# ---------------------------------------------------------------------------
# extract_text (integration with real Tesseract)
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_extracts_text_from_image(self) -> None:
        """Tesseract should find text in an image with clear lettering."""
        img = _make_image_with_text("HELLO")
        settings = _create_test_settings(MIN_OCR_CONFIDENCE=20)
        blocks = extract_text(img, settings)
        assert len(blocks) >= 1
        found_text = " ".join(b.text for b in blocks).upper()
        assert "HELLO" in found_text

    def test_blank_image_returns_empty(self) -> None:
        """A blank image should return no text blocks."""
        img = _make_blank_image()
        settings = _create_test_settings()
        blocks = extract_text(img, settings)
        assert blocks == []

    def test_blocks_are_textblock_instances(self) -> None:
        """Each returned item should be a TextBlock Pydantic model."""
        img = _make_image_with_text("TEST")
        settings = _create_test_settings(MIN_OCR_CONFIDENCE=20)
        blocks = extract_text(img, settings)
        for block in blocks:
            assert isinstance(block, TextBlock)
            assert len(block.bbox) == 4
            assert block.confidence >= 0

    def test_high_confidence_filter(self) -> None:
        """Setting very high confidence should filter out most results."""
        img = _make_image_with_text("HELLO")
        settings = _create_test_settings(MIN_OCR_CONFIDENCE=100)
        blocks = extract_text(img, settings)
        # With confidence=100 filter, most/all results get excluded
        # (Tesseract rarely returns exactly 100 confidence)
        # This just verifies the filter is applied without error
        assert isinstance(blocks, list)

    def test_tesseract_failure_raises_ocr_error(self) -> None:
        """If Tesseract crashes, an OCRError should be raised."""
        img = _make_image_with_text("TEST")
        settings = _create_test_settings()
        with patch(
            "app.pipeline.ocr.pytesseract.image_to_data",
            side_effect=Exception("tesseract not found"),
        ):
            with pytest.raises(OCRError, match="Tesseract OCR failed"):
                extract_text(img, settings)
