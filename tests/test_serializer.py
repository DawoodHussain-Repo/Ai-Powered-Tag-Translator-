from __future__ import annotations

import base64

import pytest
from PIL import Image

from app.models.schemas import PipelineResult
from app.pipeline.serializer import serialize_response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image(
    size: tuple[int, int] = (100, 100),
    mode: str = "RGB",
) -> Image.Image:
    return Image.new(mode, size, color=(255, 0, 0))


# ---------------------------------------------------------------------------
# serialize_response
# ---------------------------------------------------------------------------

class TestSerializeResponse:
    def test_returns_pipeline_result(self) -> None:
        img = _make_image()
        result = serialize_response(img, "translated", "es", 3)
        assert isinstance(result, PipelineResult)

    def test_status_field(self) -> None:
        img = _make_image()
        result = serialize_response(img, "already_english", "en", 0)
        assert result.status == "already_english"

    def test_source_language_field(self) -> None:
        img = _make_image()
        result = serialize_response(img, "translated", "fr", 2)
        assert result.source_language == "fr"

    def test_source_language_none(self) -> None:
        img = _make_image()
        result = serialize_response(img, "no_text_found", None, 0)
        assert result.source_language is None

    def test_blocks_translated_field(self) -> None:
        img = _make_image()
        result = serialize_response(img, "translated", "es", 5)
        assert result.blocks_translated == 5

    def test_output_format_is_jpeg(self) -> None:
        img = _make_image()
        result = serialize_response(img, "translated", "es", 1)
        assert result.output_format == "jpeg"

    def test_output_image_is_valid_base64(self) -> None:
        img = _make_image()
        result = serialize_response(img, "translated", "es", 1)
        # Should decode without error
        decoded = base64.b64decode(result.output_image)
        assert len(decoded) > 0

    def test_output_image_is_valid_jpeg(self) -> None:
        img = _make_image()
        result = serialize_response(img, "translated", "es", 1)
        decoded = base64.b64decode(result.output_image)
        # JPEG files start with FF D8
        assert decoded[:2] == b"\xff\xd8"

    def test_rgba_image_converted(self) -> None:
        """RGBA images should be converted to RGB for JPEG encoding."""
        img = _make_image(mode="RGBA")
        result = serialize_response(img, "translated", "es", 1)
        decoded = base64.b64decode(result.output_image)
        assert decoded[:2] == b"\xff\xd8"

    def test_verification_failed_status(self) -> None:
        img = _make_image()
        result = serialize_response(img, "verification_failed", "es", 2)
        assert result.status == "verification_failed"

    def test_result_is_frozen(self) -> None:
        """PipelineResult should be immutable (frozen model)."""
        img = _make_image()
        result = serialize_response(img, "translated", "es", 1)
        with pytest.raises(Exception):
            result.status = "already_english"  # type: ignore[misc]
