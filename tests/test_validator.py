from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image

from app.config import Settings
from app.exceptions import ValidationError
from app.pipeline.validator import (
    validate_extension,
    validate_file_size,
    validate_image_opens,
    validate_input,
    validate_mime,
)


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


def _make_image_bytes(fmt: str = "PNG", size: tuple[int, int] = (100, 100)) -> bytes:
    """Create a minimal valid image in the given format and return its bytes."""
    img = Image.new("RGB", size, color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# validate_extension
# ---------------------------------------------------------------------------

class TestValidateExtension:
    def test_valid_jpg(self) -> None:
        validate_extension("photo.jpg")

    def test_valid_jpeg(self) -> None:
        validate_extension("photo.jpeg")

    def test_valid_png(self) -> None:
        validate_extension("photo.png")

    def test_valid_webp(self) -> None:
        validate_extension("photo.webp")

    def test_valid_uppercase(self) -> None:
        validate_extension("PHOTO.PNG")

    def test_invalid_gif(self) -> None:
        with pytest.raises(ValidationError, match="not allowed"):
            validate_extension("animation.gif")

    def test_invalid_no_extension(self) -> None:
        with pytest.raises(ValidationError, match="not allowed"):
            validate_extension("noext")

    def test_invalid_txt(self) -> None:
        with pytest.raises(ValidationError, match="not allowed"):
            validate_extension("document.txt")


# ---------------------------------------------------------------------------
# validate_mime
# ---------------------------------------------------------------------------

class TestValidateMime:
    def test_valid_png(self) -> None:
        img_bytes = _make_image_bytes("PNG")
        validate_mime(img_bytes)

    def test_valid_jpeg(self) -> None:
        img_bytes = _make_image_bytes("JPEG")
        validate_mime(img_bytes)

    def test_valid_webp(self) -> None:
        img_bytes = _make_image_bytes("WEBP")
        validate_mime(img_bytes)

    def test_invalid_text(self) -> None:
        with pytest.raises(ValidationError, match="not allowed"):
            validate_mime(b"This is plain text, not an image")

    def test_invalid_gif(self) -> None:
        img = Image.new("RGB", (10, 10))
        buf = BytesIO()
        img.save(buf, format="GIF")
        with pytest.raises(ValidationError, match="not allowed"):
            validate_mime(buf.getvalue())


# ---------------------------------------------------------------------------
# validate_file_size
# ---------------------------------------------------------------------------

class TestValidateFileSize:
    def test_within_limit(self) -> None:
        settings = _create_test_settings(MAX_FILE_SIZE_MB=1)
        small = b"x" * (1024 * 1024 - 1)  # Just under 1 MB
        validate_file_size(small, settings)

    def test_at_limit(self) -> None:
        settings = _create_test_settings(MAX_FILE_SIZE_MB=1)
        exact = b"x" * (1024 * 1024)  # Exactly 1 MB
        validate_file_size(exact, settings)

    def test_exceeds_limit(self) -> None:
        settings = _create_test_settings(MAX_FILE_SIZE_MB=1)
        big = b"x" * (1024 * 1024 + 1)  # 1 byte over
        with pytest.raises(ValidationError, match="exceeds"):
            validate_file_size(big, settings)


# ---------------------------------------------------------------------------
# validate_image_opens
# ---------------------------------------------------------------------------

class TestValidateImageOpens:
    def test_valid_png(self) -> None:
        img_bytes = _make_image_bytes("PNG")
        result = validate_image_opens(img_bytes)
        assert isinstance(result, Image.Image)
        assert result.size == (100, 100)

    def test_valid_jpeg(self) -> None:
        img_bytes = _make_image_bytes("JPEG")
        result = validate_image_opens(img_bytes)
        assert isinstance(result, Image.Image)

    def test_corrupt_data(self) -> None:
        with pytest.raises(ValidationError, match="corrupt"):
            validate_image_opens(b"not an image at all")

    def test_truncated_png(self) -> None:
        img_bytes = _make_image_bytes("PNG")
        truncated = img_bytes[:50]  # Cut off most of the file
        with pytest.raises(ValidationError, match="corrupt"):
            validate_image_opens(truncated)


# ---------------------------------------------------------------------------
# validate_input (integration of all checks)
# ---------------------------------------------------------------------------

class TestValidateInput:
    def test_valid_png_file(self) -> None:
        settings = _create_test_settings()
        img_bytes = _make_image_bytes("PNG")
        result = validate_input("product.png", img_bytes, settings)
        assert isinstance(result, Image.Image)

    def test_valid_jpeg_file(self) -> None:
        settings = _create_test_settings()
        img_bytes = _make_image_bytes("JPEG")
        result = validate_input("product.jpg", img_bytes, settings)
        assert isinstance(result, Image.Image)

    def test_rejects_bad_extension_before_other_checks(self) -> None:
        settings = _create_test_settings()
        img_bytes = _make_image_bytes("PNG")
        with pytest.raises(ValidationError, match="not allowed"):
            validate_input("product.bmp", img_bytes, settings)

    def test_rejects_oversized_file(self) -> None:
        settings = _create_test_settings(MAX_FILE_SIZE_MB=0)
        img_bytes = _make_image_bytes("PNG")
        with pytest.raises(ValidationError, match="exceeds"):
            validate_input("product.png", img_bytes, settings)
