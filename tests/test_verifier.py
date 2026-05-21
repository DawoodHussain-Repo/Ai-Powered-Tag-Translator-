from __future__ import annotations

from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.pipeline.verifier import verify_output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image_with_text(text: str = "HELLO WORLD") -> Image.Image:
    """Create a test image with visible text on a white background."""
    img = Image.new("RGB", (400, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("assets/fonts/NotoSans-Regular.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 20), text, fill=(0, 0, 0), font=font)
    return img


def _make_blank_image() -> Image.Image:
    """Create a blank white image with no text."""
    return Image.new("RGB", (200, 200), color=(255, 255, 255))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestVerifyOutput:
    """Tests for the heuristic presence check verifier."""

    def test_image_with_text_passes(self) -> None:
        """An image with clear alphabetic text should pass."""
        img = _make_image_with_text("TRANSLATED TEXT")
        result = verify_output(img)
        assert result == "pass"

    def test_blank_image_fails(self) -> None:
        """A blank image with no text should fail."""
        img = _make_blank_image()
        result = verify_output(img)
        assert result == "fail"

    def test_empty_ocr_output_fails(self) -> None:
        """If OCR returns empty string, should fail."""
        img = _make_image_with_text("TEST")
        with patch(
            "app.pipeline.verifier.pytesseract.image_to_string",
            return_value="",
        ):
            result = verify_output(img)
            assert result == "fail"

    def test_only_numbers_fails(self) -> None:
        """Text containing only numbers (no alphabetic tokens > 2) should fail."""
        img = _make_image_with_text("123")
        with patch(
            "app.pipeline.verifier.pytesseract.image_to_string",
            return_value="12345 67890",
        ):
            result = verify_output(img)
            assert result == "fail"

    def test_only_symbols_fails(self) -> None:
        """Text containing only symbols should fail."""
        img = _make_image_with_text("...")
        with patch(
            "app.pipeline.verifier.pytesseract.image_to_string",
            return_value="... --- !!!",
        ):
            result = verify_output(img)
            assert result == "fail"

    def test_short_alpha_tokens_fail(self) -> None:
        """Alphabetic tokens of length <= 2 should not pass the check."""
        img = _make_image_with_text("AB")
        with patch(
            "app.pipeline.verifier.pytesseract.image_to_string",
            return_value="A B AB",
        ):
            result = verify_output(img)
            assert result == "fail"

    def test_mixed_text_with_long_token_passes(self) -> None:
        """Text with at least one alphabetic token > 2 chars should pass."""
        img = _make_image_with_text("OK")
        with patch(
            "app.pipeline.verifier.pytesseract.image_to_string",
            return_value="123 Hello 456",
        ):
            result = verify_output(img)
            assert result == "pass"

    def test_tesseract_exception_fails(self) -> None:
        """If Tesseract crashes, should return fail."""
        img = _make_image_with_text("TEST")
        with patch(
            "app.pipeline.verifier.pytesseract.image_to_string",
            side_effect=Exception("tesseract crashed"),
        ):
            result = verify_output(img)
            assert result == "fail"

    def test_whitespace_only_fails(self) -> None:
        """Whitespace-only OCR output should fail."""
        img = _make_image_with_text("TEST")
        with patch(
            "app.pipeline.verifier.pytesseract.image_to_string",
            return_value="   \n  \t  ",
        ):
            result = verify_output(img)
            assert result == "fail"

    def test_three_char_alpha_token_passes(self) -> None:
        """A 3-character alphabetic token (length > 2) should pass."""
        img = _make_image_with_text("THE")
        with patch(
            "app.pipeline.verifier.pytesseract.image_to_string",
            return_value="THE",
        ):
            result = verify_output(img)
            assert result == "pass"
