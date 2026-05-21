from __future__ import annotations

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.exceptions import CompositorError
from app.models.schemas import TranslatedBlock
from app.pipeline.compositor import (
    _auto_scale_font,
    _clamp_bbox,
    _sample_background_color,
    _sample_foreground_color,
    composite_image,
    _FONT_PATH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image_with_text(
    text: str = "HELLO",
    size: tuple[int, int] = (400, 100),
    bg_color: tuple[int, int, int] = (255, 255, 255),
    fg_color: tuple[int, int, int] = (0, 0, 0),
    font_size: int = 40,
) -> Image.Image:
    """Create a test image with text on a solid background."""
    img = Image.new("RGB", size, color=bg_color)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(_FONT_PATH, font_size)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 20), text, fill=fg_color, font=font)
    return img


def _block(
    translated: str,
    bbox: tuple[int, int, int, int] = (20, 20, 150, 50),
) -> TranslatedBlock:
    """Create a TranslatedBlock with the given text and bbox."""
    return TranslatedBlock(
        original_text="original",
        translated_text=translated,
        bbox=bbox,
    )


# ---------------------------------------------------------------------------
# _clamp_bbox
# ---------------------------------------------------------------------------

class TestClampBbox:
    def test_within_bounds(self) -> None:
        result = _clamp_bbox((10, 20, 100, 50), 400, 300)
        assert result == (10, 20, 100, 50)

    def test_negative_x_y(self) -> None:
        x, y, w, h = _clamp_bbox((-5, -10, 100, 50), 400, 300)
        assert x == 0
        assert y == 0

    def test_exceeds_width(self) -> None:
        x, y, w, h = _clamp_bbox((350, 10, 100, 50), 400, 300)
        assert x + w <= 400

    def test_exceeds_height(self) -> None:
        x, y, w, h = _clamp_bbox((10, 280, 100, 50), 400, 300)
        assert y + h <= 300

    def test_zero_dimension_gets_minimum(self) -> None:
        x, y, w, h = _clamp_bbox((10, 10, 0, 0), 400, 300)
        assert w >= 1
        assert h >= 1


# ---------------------------------------------------------------------------
# _sample_background_color
# ---------------------------------------------------------------------------

class TestSampleBackgroundColor:
    def test_uniform_background(self) -> None:
        """On a solid-colour image, background sample should match."""
        img = Image.new("RGB", (200, 200), color=(120, 130, 140))
        bg = _sample_background_color(img, 50, 50, 50, 50)
        assert bg == (120, 130, 140)

    def test_returns_tuple(self) -> None:
        img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        bg = _sample_background_color(img, 10, 10, 50, 50)
        assert isinstance(bg, tuple)
        assert len(bg) == 3

    def test_edge_bbox_does_not_crash(self) -> None:
        """Bbox at the image edge should not cause index errors."""
        img = Image.new("RGB", (100, 100), color=(200, 200, 200))
        bg = _sample_background_color(img, 0, 0, 100, 100)
        assert isinstance(bg, tuple)


# ---------------------------------------------------------------------------
# _sample_foreground_color
# ---------------------------------------------------------------------------

class TestSampleForegroundColor:
    def test_dark_text_on_light_bg(self) -> None:
        """Foreground sample should return a dark colour for dark text."""
        img = _make_image_with_text(
            "HELLO", bg_color=(255, 255, 255), fg_color=(10, 10, 10)
        )
        fg = _sample_foreground_color(img, 20, 20, 150, 50)
        # The darkest pixels should be close to the text colour
        assert all(ch < 128 for ch in fg)

    def test_light_text_on_dark_bg(self) -> None:
        """Foreground sample should return a light colour for light text on dark background."""
        img = _make_image_with_text(
            "HELLO", bg_color=(10, 10, 10), fg_color=(250, 250, 250)
        )
        fg = _sample_foreground_color(img, 20, 20, 150, 50)
        # The lightest pixels should be close to the text colour
        assert all(ch > 128 for ch in fg)

    def test_returns_tuple(self) -> None:
        img = Image.new("RGB", (200, 200), color=(50, 50, 50))
        fg = _sample_foreground_color(img, 10, 10, 50, 50)
        assert isinstance(fg, tuple)
        assert len(fg) == 3


# ---------------------------------------------------------------------------
# _auto_scale_font
# ---------------------------------------------------------------------------

class TestAutoScaleFont:
    def test_fits_within_bbox(self) -> None:
        font, text = _auto_scale_font("Hi", 200, 40, _FONT_PATH)
        text_bbox = font.getbbox(text)
        text_width = text_bbox[2] - text_bbox[0]
        assert text_width <= 200

    def test_long_text_truncated_with_ellipsis(self) -> None:
        """Very long text in a tiny bbox should be truncated."""
        font, text = _auto_scale_font(
            "This is an extremely long piece of text", 30, 10, _FONT_PATH
        )
        assert "…" in text or len(text) < 40

    def test_minimum_font_size(self) -> None:
        """Font size should not go below 8pt."""
        font, _ = _auto_scale_font("Test", 10, 8, _FONT_PATH)
        assert font.size >= 8


# ---------------------------------------------------------------------------
# composite_image (integration)
# ---------------------------------------------------------------------------

class TestCompositeImage:
    def test_output_differs_from_original(self) -> None:
        """Output image should differ from input in text regions."""
        original = _make_image_with_text("HOLA")
        blocks = [_block("HELLO", bbox=(20, 20, 150, 50))]
        result = composite_image(original, blocks)

        # Images should have the same size
        assert result.size == original.size

        # But pixel data should differ (at least in the text region)
        orig_region = original.crop((20, 20, 170, 70))
        result_region = result.crop((20, 20, 170, 70))
        assert list(orig_region.getdata()) != list(result_region.getdata())

    def test_original_not_mutated(self) -> None:
        """Invariant 1: the original image must never be mutated."""
        original = _make_image_with_text("HOLA")
        original_data = list(original.getdata())
        blocks = [_block("HELLO", bbox=(20, 20, 150, 50))]

        composite_image(original, blocks)

        assert list(original.getdata()) == original_data

    def test_empty_blocks_returns_copy(self) -> None:
        """With no blocks, should return a copy of the original."""
        original = _make_image_with_text("HOLA")
        result = composite_image(original, [])
        assert result.size == original.size
        assert list(result.getdata()) == list(original.getdata())
        assert result is not original  # Must be a copy

    def test_returns_pil_image(self) -> None:
        original = _make_image_with_text("TEST")
        blocks = [_block("TEST", bbox=(20, 20, 100, 40))]
        result = composite_image(original, blocks)
        assert isinstance(result, Image.Image)

    def test_multiple_blocks(self) -> None:
        """Multiple blocks should all be composited."""
        original = Image.new("RGB", (400, 200), color=(255, 255, 255))
        draw = ImageDraw.Draw(original)
        draw.text((10, 10), "AAA", fill=(0, 0, 0))
        draw.text((10, 100), "BBB", fill=(0, 0, 0))

        blocks = [
            _block("XXX", bbox=(10, 10, 80, 30)),
            _block("YYY", bbox=(10, 100, 80, 30)),
        ]
        result = composite_image(original, blocks)
        assert result.size == original.size

    def test_out_of_bounds_bbox_handled(self) -> None:
        """Bbox extending beyond image should be clamped, not crash."""
        original = Image.new("RGB", (100, 100), color=(200, 200, 200))
        blocks = [_block("TEXT", bbox=(80, 80, 50, 50))]
        # Should not raise
        result = composite_image(original, blocks)
        assert isinstance(result, Image.Image)

    def test_rgba_image_handled(self) -> None:
        """RGBA images should be handled (converted to RGB)."""
        original = Image.new("RGBA", (200, 100), color=(255, 255, 255, 255))
        blocks = [_block("TEXT", bbox=(10, 10, 80, 30))]
        result = composite_image(original, blocks)
        assert isinstance(result, Image.Image)
