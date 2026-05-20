from __future__ import annotations

from unittest.mock import patch

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.pipeline.verifier import verify_output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FONT_PATH = "assets/fonts/NotoSans-Regular.ttf"


def _make_image_with_text(
    text: str,
    size: tuple[int, int] = (400, 100),
    font_size: int = 40,
) -> Image.Image:
    """Create a test image with clear text on a white background."""
    img = Image.new("RGB", size, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(_FONT_PATH, font_size)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 20), text, fill=(0, 0, 0), font=font)
    return img


def _make_blank_image() -> Image.Image:
    return Image.new("RGB", (200, 200), color=(255, 255, 255))


# ---------------------------------------------------------------------------
# verify_output
# ---------------------------------------------------------------------------

class TestVerifyOutput:
    def test_english_text_passes(self) -> None:
        """Image with English text should return 'pass'."""
        img = _make_image_with_text("Hello World Testing")
        result = verify_output(img)
        assert result == "pass"

    def test_blank_image_fails(self) -> None:
        """Image with no text should return 'fail'."""
        img = _make_blank_image()
        result = verify_output(img)
        assert result == "fail"

    def test_non_english_text_fails(self) -> None:
        """Image with non-English text should return 'fail'."""
        img = _make_image_with_text("Esta es una prueba en espanol")
        result = verify_output(img)
        assert result == "fail"

    def test_tesseract_failure_returns_fail(self) -> None:
        """If Tesseract crashes, should return 'fail' not raise."""
        img = _make_image_with_text("Hello")
        with patch(
            "app.pipeline.verifier.pytesseract.image_to_string",
            side_effect=Exception("tesseract error"),
        ):
            result = verify_output(img)
            assert result == "fail"

    def test_langdetect_failure_returns_fail(self) -> None:
        """If langdetect crashes, should return 'fail' not raise."""
        img = _make_image_with_text("Hello")
        with patch(
            "app.pipeline.verifier.detect",
            side_effect=Exception("detection error"),
        ):
            result = verify_output(img)
            assert result == "fail"

    def test_retry_scenario_mock(self) -> None:
        """Simulate: first call returns 'fail', verifying retry is needed.

        This tests that verify_output can be called twice and returns
        different results based on the image content.
        """
        # First call with Spanish text
        spanish_img = _make_image_with_text("Hola Mundo prueba texto")
        first_result = verify_output(spanish_img)
        assert first_result == "fail"

        # Second call with English text (after retry translation)
        english_img = _make_image_with_text("Hello World test text")
        second_result = verify_output(english_img)
        assert second_result == "pass"
