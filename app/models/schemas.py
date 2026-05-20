from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TextBlock(BaseModel):
    """A single block of text extracted by OCR with its bounding box.

    Produced by Node 2 (OCRExtractor).
    """

    model_config = ConfigDict(frozen=True)

    text: str
    bbox: tuple[int, int, int, int]
    confidence: float


class TranslatedBlock(BaseModel):
    """A text block after translation, mapping original to translated text.

    Produced by Node 4 (TextTranslator).
    """

    model_config = ConfigDict(frozen=True)

    original_text: str
    translated_text: str
    bbox: tuple[int, int, int, int]


class PipelineResult(BaseModel):
    """Final response payload returned by the API.

    Produced by Node 7 (ResponseSerializer).
    """

    model_config = ConfigDict(frozen=True)

    status: Literal[
        "translated",
        "already_english",
        "no_text_found",
        "verification_failed",
    ]
    source_language: str | None
    blocks_translated: int
    output_image: str
    output_format: Literal["jpeg"]


class ErrorResponse(BaseModel):
    """Structured error response for 400 and 500 status codes."""

    model_config = ConfigDict(frozen=True)

    error: str
    code: str
