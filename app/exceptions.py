from __future__ import annotations


class PipelineError(Exception):
    """Base exception for all pipeline-related errors.

    The route handler catches this base class to map domain exceptions
    to HTTP error responses.
    """


class ValidationError(PipelineError):
    """Raised by Node 1 (InputValidator) when the uploaded file fails
    extension, MIME type, file size, or PIL open checks."""


class OCRError(PipelineError):
    """Raised by Node 2 (OCRExtractor) when OCR processing fails
    unexpectedly."""


class TranslationError(PipelineError):
    """Raised by Node 4 (TextTranslator) when the Gemini API call fails
    or the response cannot be parsed as valid JSON."""


class CompositorError(PipelineError):
    """Raised by Node 5 (ImageCompositor) when image compositing fails
    during text erasure or rendering."""
