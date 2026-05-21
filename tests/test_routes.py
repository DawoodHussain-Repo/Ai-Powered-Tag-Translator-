from __future__ import annotations

import base64
from io import BytesIO
from unittest.mock import ANY, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import get_settings, Settings
from app.exceptions import CompositorError, TranslationError, ValidationError
from app.main import app
from app.models.schemas import TextBlock, TranslatedBlock
from app.pipeline.language import LanguageResult


client = TestClient(app)


@pytest.fixture(autouse=True)
def override_settings() -> None:
    def get_test_settings() -> Settings:
        return Settings(
            GEMINI_API_KEY="test-key-not-real",
            MAX_FILE_SIZE_MB=10,
            MIN_OCR_CONFIDENCE=40,
            MIN_BBOX_AREA=100,
            GEMINI_MODEL="gemini-1.5-flash",
            LANGDETECT_MIN_CONFIDENCE=0.9,
        )
    app.dependency_overrides[get_settings] = get_test_settings
    yield
    app.dependency_overrides.pop(get_settings, None)


def _make_image_bytes(fmt: str = "PNG") -> bytes:
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# POST /api/v1/translate-image tests
# ---------------------------------------------------------------------------

class TestTranslateImageRoute:
    def test_rejects_invalid_extension(self) -> None:
        """Route handler directly rejects invalid extensions with 400."""
        response = client.post(
            "/api/v1/translate-image",
            files={"file": ("test.gif", b"fake gif content", "image/gif")},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "INVALID_FILE_TYPE"
        assert "extension" in data["error"].lower()

    def test_rejects_invalid_content_type(self) -> None:
        """Route handler directly rejects invalid Content-Type with 400."""
        response = client.post(
            "/api/v1/translate-image",
            files={"file": ("test.png", b"fake png content", "text/plain")},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "INVALID_FILE_TYPE"
        assert "content-type" in data["error"].lower()

    @patch("app.api.routes.validate_input")
    def test_validation_error_from_node_1(self, mock_validate: MagicMock) -> None:
        """A ValidationError raised from Node 1 is returned as a 400."""
        mock_validate.side_effect = ValidationError("Invalid file size", code="INVALID_FILE_SIZE")
        img_bytes = _make_image_bytes("PNG")
        response = client.post(
            "/api/v1/translate-image",
            files={"file": ("test.png", img_bytes, "image/png")},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "INVALID_FILE_SIZE"
        assert data["error"] == "Invalid file size"

    @patch("app.api.routes.validate_input")
    @patch("app.api.routes.preprocess_for_ocr")
    @patch("app.api.routes.extract_text")
    def test_no_text_found_early_return(
        self, mock_extract: MagicMock, mock_preprocess: MagicMock, mock_validate: MagicMock
    ) -> None:
        """If OCR finds no text, return 200 with status 'no_text_found'."""
        mock_img = Image.new("RGB", (10, 10))
        mock_validate.return_value = mock_img
        mock_preprocess.return_value = mock_img
        mock_extract.return_value = []  # No text blocks found

        img_bytes = _make_image_bytes("PNG")
        response = client.post(
            "/api/v1/translate-image",
            files={"file": ("test.png", img_bytes, "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "no_text_found"
        assert data["blocks_translated"] == 0
        assert data["source_language"] is None

    @patch("app.api.routes.validate_input")
    @patch("app.api.routes.preprocess_for_ocr")
    @patch("app.api.routes.extract_text")
    @patch("app.api.routes.detect_language")
    def test_already_english_early_return(
        self,
        mock_detect: MagicMock,
        mock_extract: MagicMock,
        mock_preprocess: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        """If source language is English, return 200 with status 'already_english'."""
        mock_img = Image.new("RGB", (10, 10))
        mock_validate.return_value = mock_img
        mock_preprocess.return_value = mock_img
        mock_extract.return_value = [
            TextBlock(text="English text", bbox=(0, 0, 5, 5), confidence=99)
        ]
        mock_detect.return_value = LanguageResult(language_code="en", is_english=True)

        img_bytes = _make_image_bytes("PNG")
        response = client.post(
            "/api/v1/translate-image",
            files={"file": ("test.png", img_bytes, "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "already_english"
        assert data["source_language"] == "en"
        assert data["blocks_translated"] == 0

    @patch("app.api.routes.validate_input")
    @patch("app.api.routes.preprocess_for_ocr")
    @patch("app.api.routes.extract_text")
    @patch("app.api.routes.detect_language")
    @patch("app.api.routes.translate_blocks")
    @patch("app.api.routes.composite_image")
    @patch("app.api.routes.verify_output")
    def test_successful_translation_path_1(
        self,
        mock_verify: MagicMock,
        mock_composite: MagicMock,
        mock_translate: MagicMock,
        mock_detect: MagicMock,
        mock_extract: MagicMock,
        mock_preprocess: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        """Success path where the first translation verification passes."""
        mock_img = Image.new("RGB", (10, 10))
        mock_validate.return_value = mock_img
        mock_preprocess.return_value = mock_img
        mock_extract.return_value = [
            TextBlock(text="Hola", bbox=(0, 0, 5, 5), confidence=99)
        ]
        mock_detect.return_value = LanguageResult(language_code="es", is_english=False)
        mock_translate.return_value = [
            TranslatedBlock(original_text="Hola", translated_text="Hello", bbox=(0, 0, 5, 5))
        ]
        mock_composite.return_value = mock_img
        mock_verify.return_value = "pass"

        img_bytes = _make_image_bytes("PNG")
        response = client.post(
            "/api/v1/translate-image",
            files={"file": ("test.png", img_bytes, "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "translated"
        assert data["source_language"] == "es"
        assert data["blocks_translated"] == 1
        # Mock verify should only be called once (no retry needed)
        mock_verify.assert_called_once()

    @patch("app.api.routes.validate_input")
    @patch("app.api.routes.preprocess_for_ocr")
    @patch("app.api.routes.extract_text")
    @patch("app.api.routes.detect_language")
    @patch("app.api.routes.translate_blocks")
    @patch("app.api.routes.composite_image")
    @patch("app.api.routes.verify_output")
    def test_successful_translation_path_2_retry(
        self,
        mock_verify: MagicMock,
        mock_composite: MagicMock,
        mock_translate: MagicMock,
        mock_detect: MagicMock,
        mock_extract: MagicMock,
        mock_preprocess: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        """Retry path where the first verification fails but the second passes."""
        mock_img = Image.new("RGB", (10, 10))
        mock_validate.return_value = mock_img
        mock_preprocess.return_value = mock_img
        mock_extract.return_value = [
            TextBlock(text="Hola", bbox=(0, 0, 5, 5), confidence=99)
        ]
        mock_detect.return_value = LanguageResult(language_code="es", is_english=False)

        # Translation mock returns original attempt, then retry attempt
        t1 = TranslatedBlock(original_text="Hola", translated_text="Hello Attempt 1", bbox=(0, 0, 5, 5))
        t2 = TranslatedBlock(original_text="Hola", translated_text="Hello Attempt 2", bbox=(0, 0, 5, 5))
        mock_translate.side_effect = [[t1], [t2]]

        mock_composite.return_value = mock_img
        # Verification mock returns fail, then pass
        mock_verify.side_effect = ["fail", "pass"]

        img_bytes = _make_image_bytes("PNG")
        response = client.post(
            "/api/v1/translate-image",
            files={"file": ("test.png", img_bytes, "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "translated"
        assert data["blocks_translated"] == 1
        # Translate blocks called twice (first with retry=False, second with retry=True)
        assert mock_translate.call_count == 2
        mock_translate.assert_any_call(
            blocks=mock_extract.return_value,
            source_language="es",
            settings=ANY,
            retry=False,
        )
        mock_translate.assert_any_call(
            blocks=mock_extract.return_value,
            source_language="es",
            settings=ANY,
            retry=True,
        )

    @patch("app.api.routes.validate_input")
    @patch("app.api.routes.preprocess_for_ocr")
    @patch("app.api.routes.extract_text")
    @patch("app.api.routes.detect_language")
    @patch("app.api.routes.translate_blocks")
    @patch("app.api.routes.composite_image")
    @patch("app.api.routes.verify_output")
    def test_verification_failed_after_retry(
        self,
        mock_verify: MagicMock,
        mock_composite: MagicMock,
        mock_translate: MagicMock,
        mock_detect: MagicMock,
        mock_extract: MagicMock,
        mock_preprocess: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        """If both attempts fail verification, return 200 with status 'verification_failed'."""
        mock_img = Image.new("RGB", (10, 10))
        mock_validate.return_value = mock_img
        mock_preprocess.return_value = mock_img
        mock_extract.return_value = [
            TextBlock(text="Hola", bbox=(0, 0, 5, 5), confidence=99)
        ]
        mock_detect.return_value = LanguageResult(language_code="es", is_english=False)
        mock_translate.return_value = [
            TranslatedBlock(original_text="Hola", translated_text="Fail Text", bbox=(0, 0, 5, 5))
        ]
        mock_composite.return_value = mock_img
        # Verification fails both times
        mock_verify.side_effect = ["fail", "fail"]

        img_bytes = _make_image_bytes("PNG")
        response = client.post(
            "/api/v1/translate-image",
            files={"file": ("test.png", img_bytes, "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "verification_failed"
        assert data["source_language"] == "es"
        assert data["blocks_translated"] == 1

    @patch("app.api.routes.validate_input")
    @patch("app.api.routes.preprocess_for_ocr")
    @patch("app.api.routes.extract_text")
    @patch("app.api.routes.detect_language")
    @patch("app.api.routes.translate_blocks")
    def test_translation_error_raises_500(
        self,
        mock_translate: MagicMock,
        mock_detect: MagicMock,
        mock_extract: MagicMock,
        mock_preprocess: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        """A TranslationError maps to 500 with TRANSLATION_FAILED code."""
        mock_img = Image.new("RGB", (10, 10))
        mock_validate.return_value = mock_img
        mock_preprocess.return_value = mock_img
        mock_extract.return_value = [
            TextBlock(text="Hola", bbox=(0, 0, 5, 5), confidence=99)
        ]
        mock_detect.return_value = LanguageResult(language_code="es", is_english=False)
        mock_translate.side_effect = TranslationError("Gemini quota exceeded")

        img_bytes = _make_image_bytes("PNG")
        response = client.post(
            "/api/v1/translate-image",
            files={"file": ("test.png", img_bytes, "image/png")},
        )
        assert response.status_code == 500
        data = response.json()
        assert data["code"] == "TRANSLATION_FAILED"
        assert data["error"] == "Gemini quota exceeded"

    @patch("app.api.routes.validate_input")
    @patch("app.api.routes.preprocess_for_ocr")
    @patch("app.api.routes.extract_text")
    @patch("app.api.routes.detect_language")
    @patch("app.api.routes.translate_blocks")
    @patch("app.api.routes.composite_image")
    def test_compositor_error_raises_500(
        self,
        mock_composite: MagicMock,
        mock_translate: MagicMock,
        mock_detect: MagicMock,
        mock_extract: MagicMock,
        mock_preprocess: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        """A CompositorError maps to 500 with COMPOSITOR_FAILED code."""
        mock_img = Image.new("RGB", (10, 10))
        mock_validate.return_value = mock_img
        mock_preprocess.return_value = mock_img
        mock_extract.return_value = [
            TextBlock(text="Hola", bbox=(0, 0, 5, 5), confidence=99)
        ]
        mock_detect.return_value = LanguageResult(language_code="es", is_english=False)
        mock_translate.return_value = [
            TranslatedBlock(original_text="Hola", translated_text="Hello", bbox=(0, 0, 5, 5))
        ]
        mock_composite.side_effect = CompositorError("Compositing failed")

        img_bytes = _make_image_bytes("PNG")
        response = client.post(
            "/api/v1/translate-image",
            files={"file": ("test.png", img_bytes, "image/png")},
        )
        assert response.status_code == 500
        data = response.json()
        assert data["code"] == "COMPOSITOR_FAILED"
        assert data["error"] == "Compositing failed"
