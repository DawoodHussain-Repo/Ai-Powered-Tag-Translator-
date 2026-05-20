from __future__ import annotations

from io import BytesIO

import magic
from PIL import Image

from app.config import Settings
from app.exceptions import ValidationError

# Allowed extensions and their corresponding MIME types
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp"})
ALLOWED_MIMES: frozenset[str] = frozenset({
    "image/jpeg",
    "image/png",
    "image/webp",
})


def validate_extension(filename: str) -> None:
    """Check that the file extension is in the allowlist.

    Raises ``ValidationError`` with code ``INVALID_FILE_TYPE`` if the
    extension is not one of jpg, jpeg, png, or webp.
    """
    import os

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"File extension '{ext}' is not allowed. "
            f"Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )


def validate_mime(file_bytes: bytes) -> None:
    """Sniff the MIME type from the raw file bytes.

    Raises ``ValidationError`` with code ``INVALID_FILE_TYPE`` if the
    detected MIME type is not an allowed image format.
    """
    detected = magic.from_buffer(file_bytes, mime=True)
    if detected not in ALLOWED_MIMES:
        raise ValidationError(
            f"MIME type '{detected}' is not allowed. "
            f"Accepted: {', '.join(sorted(ALLOWED_MIMES))}"
        )


def validate_file_size(file_bytes: bytes, settings: Settings) -> None:
    """Check that the file does not exceed the configured size limit.

    Raises ``ValidationError`` with code ``INVALID_FILE_SIZE`` if the
    file is larger than ``MAX_FILE_SIZE_MB``.
    """
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise ValidationError(
            f"File size {len(file_bytes)} bytes exceeds the "
            f"{settings.MAX_FILE_SIZE_MB} MB limit."
        )


def validate_image_opens(file_bytes: bytes) -> Image.Image:
    """Attempt to open the file as a PIL Image.

    Returns the opened ``PIL.Image.Image`` on success.
    Raises ``ValidationError`` with code ``CORRUPT_IMAGE`` if the file
    cannot be opened or is corrupt.
    """
    try:
        img = Image.open(BytesIO(file_bytes))
        img.verify()  # Verify integrity without loading pixel data
        # Re-open after verify() since verify() can close the image
        img = Image.open(BytesIO(file_bytes))
        img.load()  # Force full decode to catch truncated files
        return img
    except Exception as exc:
        raise ValidationError(
            f"Image file is corrupt or cannot be opened: {exc}"
        ) from exc


def validate_input(
    filename: str,
    file_bytes: bytes,
    settings: Settings,
) -> Image.Image:
    """Run all input validation checks in sequence.

    This is the main entry point for Node 1. It validates the file
    extension, MIME type, size, and attempts to open it as a PIL Image.

    Returns a validated ``PIL.Image.Image`` object on success.
    Raises ``ValidationError`` on any failure.
    """
    validate_extension(filename)
    validate_mime(file_bytes)
    validate_file_size(file_bytes, settings)
    return validate_image_opens(file_bytes)
