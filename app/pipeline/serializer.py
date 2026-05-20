from __future__ import annotations

import base64
from io import BytesIO
from typing import Literal

from PIL import Image

from app.models.schemas import PipelineResult


def serialize_response(
    image: Image.Image,
    status: Literal[
        "translated",
        "already_english",
        "no_text_found",
        "verification_failed",
    ],
    source_language: str | None,
    blocks_translated: int,
) -> PipelineResult:
    """Encode the output image and build the final response payload.

    This is the main entry point for Node 7.

    Encodes the composited image as base64 JPEG (quality=90) and
    constructs a ``PipelineResult`` Pydantic model.

    Args:
        image: The final PIL Image to encode (composited or original).
        status: Pipeline outcome status string.
        source_language: ISO 639-1 code of the detected source language.
        blocks_translated: Number of text blocks that were translated.

    Returns:
        A ``PipelineResult`` containing the base64-encoded image and
        all metadata.
    """
    # Ensure RGB mode for JPEG encoding (RGBA has no JPEG support)
    if image.mode != "RGB":
        image = image.convert("RGB")

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    b64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return PipelineResult(
        status=status,
        source_language=source_language,
        blocks_translated=blocks_translated,
        output_image=b64_image,
        output_format="jpeg",
    )
