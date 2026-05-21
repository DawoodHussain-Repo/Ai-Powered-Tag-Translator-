from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from app.pipeline.preprocessor import _sample_border_brightness, preprocess_for_ocr


class TestSampleBorderBrightness:
    """Tests for the border pixel brightness sampling helper."""

    def test_white_image_returns_high_brightness(self) -> None:
        """A fully white image should have median brightness of 255."""
        img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        brightness = _sample_border_brightness(img)
        assert brightness == 255.0

    def test_black_image_returns_low_brightness(self) -> None:
        """A fully black image should have median brightness of 0."""
        img = Image.new("RGB", (100, 100), color=(0, 0, 0))
        brightness = _sample_border_brightness(img)
        assert brightness == 0.0

    def test_dark_gray_image(self) -> None:
        """A dark gray image (50, 50, 50) should return brightness < 128."""
        img = Image.new("RGB", (100, 100), color=(50, 50, 50))
        brightness = _sample_border_brightness(img)
        assert brightness < 128

    def test_light_gray_image(self) -> None:
        """A light gray image (200, 200, 200) should return brightness >= 128."""
        img = Image.new("RGB", (100, 100), color=(200, 200, 200))
        brightness = _sample_border_brightness(img)
        assert brightness >= 128

    def test_small_image_does_not_crash(self) -> None:
        """A very small image (5x5) should not raise even though border_px=10."""
        img = Image.new("RGB", (5, 5), color=(100, 100, 100))
        brightness = _sample_border_brightness(img)
        assert 0 <= brightness <= 255


class TestPreprocessForOcr:
    """Tests for the main preprocess_for_ocr entry point."""

    def test_light_background_returns_unchanged(self) -> None:
        """A white image should be returned unchanged (pass-through)."""
        img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        result = preprocess_for_ocr(img)
        # Should be the exact same object for light backgrounds
        assert result is img

    def test_dark_background_returns_inverted_copy(self) -> None:
        """A black image should return an inverted (white) copy."""
        img = Image.new("RGB", (100, 100), color=(0, 0, 0))
        result = preprocess_for_ocr(img)
        # Should NOT be the same object
        assert result is not img
        # The inverted image should be predominantly white
        arr = np.array(result)
        assert arr.mean() > 200

    def test_dark_background_does_not_mutate_original(self) -> None:
        """The original image must never be mutated (Invariant 1)."""
        img = Image.new("RGB", (100, 100), color=(10, 10, 10))
        original_data = list(img.getdata())
        _ = preprocess_for_ocr(img)
        assert list(img.getdata()) == original_data

    def test_boundary_128_treated_as_light(self) -> None:
        """Brightness exactly 128 should be treated as light (>= 128)."""
        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        result = preprocess_for_ocr(img)
        # Should pass through unchanged
        assert result is img

    def test_rgba_image_handled(self) -> None:
        """RGBA images should be handled without error."""
        img = Image.new("RGBA", (100, 100), color=(0, 0, 0, 255))
        result = preprocess_for_ocr(img)
        # Dark background → should be inverted
        assert result is not img
        assert result.mode == "RGB"

    def test_mixed_border_dark_center_light(self) -> None:
        """Image with dark border and light center — border should dominate."""
        img = Image.new("RGB", (200, 200), color=(20, 20, 20))
        # Draw a light center rectangle (but borders stay dark)
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.rectangle([50, 50, 150, 150], fill=(240, 240, 240))
        result = preprocess_for_ocr(img)
        # Border is dark, so it should invert
        assert result is not img
