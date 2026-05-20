from __future__ import annotations


class PipelineError(Exception):
    """Base exception for all pipeline-related errors.

    The route handler catches this base class to map domain exceptions
    to HTTP error responses.
    """

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ValidationError(PipelineError):
    """Raised by Node 1 (InputValidator) when the uploaded file fails
    extension, MIME type, file size, or PIL open checks."""

    def __init__(self, message: str, code: str = "INVALID_FILE_TYPE") -> None:
        super().__init__(message, code=code)


class OCRError(PipelineError):
    """Raised by Node 2 (OCRExtractor) when OCR processing fails
    unexpectedly."""

    def __init__(self, message: str, code: str = "INTERNAL_ERROR") -> None:
        super().__init__(message, code=code)


class TranslationError(PipelineError):
    """Raised by Node 4 (TextTranslator) when the Gemini API call fails
    or the response cannot be parsed as valid JSON."""

    def __init__(self, message: str, code: str = "TRANSLATION_FAILED") -> None:
        super().__init__(message, code=code)


class CompositorError(PipelineError):
    """Raised by Node 5 (ImageCompositor) when image compositing fails
    during text erasure or rendering."""

    def __init__(self, message: str, code: str = "COMPOSITOR_FAILED") -> None:
        super().__init__(message, code=code)

