from __future__ import annotations

import os
from typing import Union

from fastapi import APIRouter, Depends, File, Response, UploadFile

from app.config import Settings, get_settings
from app.exceptions import PipelineError, ValidationError
from app.models.schemas import ErrorResponse, PipelineResult
from app.pipeline.compositor import composite_image
from app.pipeline.language import detect_language
from app.pipeline.ocr import extract_text
from app.pipeline.preprocessor import preprocess_for_ocr
from app.pipeline.serializer import serialize_response
from app.pipeline.translator import translate_blocks
from app.pipeline.validator import validate_input
from app.pipeline.verifier import verify_output

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Basic health check endpoint.

    Returns a simple status object to confirm the API is running.
    """
    return {"status": "ok"}


@router.post(
    "/translate-image",
    response_model=PipelineResult,
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def translate_image(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> Union[PipelineResult, Response]:
    """Accept an image file, translate any foreign text to English, and return it.

    This route orchestrates the entire translation pipeline:
    1. Validates the request headers and file extension.
    2. Sniffs MIME type and size, opening the image (Node 1 - InputValidator).
    3. Preprocesses the image for dark backgrounds (Node 2 - ImagePreprocessor).
    4. Runs OCR to extract text blocks (Node 3 - OCRExtractor).
    5. Detects the script/language (Node 4 - LanguageDetector).
    6. Translates the text blocks to English (Node 5 - TextTranslator).
    7. Composites the translated text onto the image (Node 6 - ImageCompositor).
    8. Verifies the output has readable text (Node 7 - OutputVerifier), retrying once on failure.
    9. Serializes and returns the final response (Node 8 - ResponseSerializer).
    """
    try:
        # Request validation (file extension, content-type header) done in the route
        filename = file.filename or ""
        ext = os.path.splitext(filename)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            raise ValidationError(
                f"File extension '{ext}' is not allowed.",
                code="INVALID_FILE_TYPE",
            )

        content_type = file.content_type or ""
        if content_type not in ["image/jpeg", "image/png", "image/webp"]:
            raise ValidationError(
                f"Content-type '{content_type}' is not allowed.",
                code="INVALID_FILE_TYPE",
            )

        file_bytes = await file.read()

        # Node 1: InputValidator (performs MIME sniffing, size check, PIL open)
        image = validate_input(filename, file_bytes, settings)

        # Node 2: ImagePreprocessor
        # Preprocessed image is used ONLY by OCRExtractor and LanguageDetector.
        # The original unmodified image is always passed to the compositor.
        preprocessed_image = preprocess_for_ocr(image)

        # Node 3: OCRExtractor (runs on preprocessed image)
        blocks = extract_text(preprocessed_image, settings)
        if not blocks:
            return serialize_response(
                image=image,
                status="no_text_found",
                source_language=None,
                blocks_translated=0,
            )

        # Node 4: LanguageDetector (OSD on preprocessed image + langdetect on OCR text)
        lang_result = detect_language(preprocessed_image, blocks, settings)
        if lang_result.is_english:
            return serialize_response(
                image=image,
                status="already_english",
                source_language=lang_result.language_code,
                blocks_translated=0,
            )

        # Node 5: TextTranslator (Attempt 1)
        translated_blocks = translate_blocks(
            blocks=blocks,
            source_language=lang_result.language_code,
            settings=settings,
            retry=False,
        )

        # Node 6: ImageCompositor (Attempt 1) — uses original image, not preprocessed
        composited_image = composite_image(image, translated_blocks)

        # Node 7: OutputVerifier (Attempt 1)
        verification_status = verify_output(preprocess_for_ocr(composited_image))

        if verification_status == "pass":
            return serialize_response(
                image=composited_image,
                status="translated",
                source_language=lang_result.language_code,
                blocks_translated=len(translated_blocks),
            )

        # Verification failed — execute single retry loop (Steps 5-6 retry)
        # Node 5: TextTranslator (Attempt 2 - Retry)
        translated_blocks_retry = translate_blocks(
            blocks=blocks,
            source_language=lang_result.language_code,
            settings=settings,
            retry=True,
        )

        # Node 6: ImageCompositor (Attempt 2 - Retry)
        composited_image_retry = composite_image(image, translated_blocks_retry)

        # Node 7: OutputVerifier (Attempt 2 - Retry)
        verification_status_retry = verify_output(preprocess_for_ocr(composited_image_retry))

        if verification_status_retry == "pass":
            return serialize_response(
                image=composited_image_retry,
                status="translated",
                source_language=lang_result.language_code,
                blocks_translated=len(translated_blocks_retry),
            )

        # Fail (second time): return 200 with partial output + status=verification_failed
        return serialize_response(
            image=composited_image_retry,
            status="verification_failed",
            source_language=lang_result.language_code,
            blocks_translated=len(translated_blocks_retry),
        )

    except ValidationError as exc:
        error_resp = ErrorResponse(error=str(exc), code=exc.code)
        return Response(
            content=error_resp.model_dump_json(),
            status_code=400,
            media_type="application/json",
        )
    except PipelineError as exc:
        error_resp = ErrorResponse(error=str(exc), code=exc.code)
        return Response(
            content=error_resp.model_dump_json(),
            status_code=500,
            media_type="application/json",
        )
    except Exception as exc:
        error_resp = ErrorResponse(
            error=f"Internal server error: {exc}",
            code="INTERNAL_ERROR",
        )
        return Response(
            content=error_resp.model_dump_json(),
            status_code=500,
            media_type="application/json",
        )
