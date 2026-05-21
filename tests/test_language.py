from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.config import Settings
from app.models.schemas import TextBlock
from app.pipeline.language import (
    LanguageResult,
    _parse_osd_script,
    _detect_with_langdetect,
    detect_language,
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
        "MIN_BBOX_AREA": 100,
        "GEMINI_MODEL": "gemini-1.5-flash",
        "LANGDETECT_MIN_CONFIDENCE": 0.9,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _make_blocks(texts: list[str]) -> list[TextBlock]:
    """Create TextBlock instances with dummy bboxes for testing."""
    return [
        TextBlock(text=t, bbox=(0, 0, 100, 20), confidence=90.0)
        for t in texts
    ]


def _make_test_image() -> Image.Image:
    """Create a simple test image."""
    return Image.new("RGB", (100, 100), color=(255, 255, 255))


# ---------------------------------------------------------------------------
# _parse_osd_script
# ---------------------------------------------------------------------------

class TestParseOsdScript:
    def test_extracts_latin(self) -> None:
        osd = "Page number: 0\nOrientation in degrees: 0\nRotate: 0\nOrientation confidence: 1.0\nScript: Latin\nScript confidence: 1.0"
        assert _parse_osd_script(osd) == "Latin"

    def test_extracts_cyrillic(self) -> None:
        osd = "Script: Cyrillic\nScript confidence: 0.9"
        assert _parse_osd_script(osd) == "Cyrillic"

    def test_extracts_arabic(self) -> None:
        osd = "Script: Arabic\nScript confidence: 0.8"
        assert _parse_osd_script(osd) == "Arabic"

    def test_unknown_when_missing(self) -> None:
        osd = "Page number: 0\nNo script line here"
        assert _parse_osd_script(osd) == "unknown"

    def test_empty_string(self) -> None:
        assert _parse_osd_script("") == "unknown"


# ---------------------------------------------------------------------------
# _detect_with_langdetect
# ---------------------------------------------------------------------------

class TestDetectWithLangdetect:
    def test_english_high_confidence(self) -> None:
        """English with high confidence should return ('en', True)."""
        with patch("app.pipeline.language.detect_langs") as mock_dl:
            mock_result = MagicMock()
            mock_result.lang = "en"
            mock_result.prob = 0.95
            mock_dl.return_value = [mock_result]

            code, is_en = _detect_with_langdetect("Hello world", 0.9)
            assert code == "en"
            assert is_en is True

    def test_spanish_high_confidence(self) -> None:
        """Spanish with high confidence returns ('es', False)."""
        with patch("app.pipeline.language.detect_langs") as mock_dl:
            mock_result = MagicMock()
            mock_result.lang = "es"
            mock_result.prob = 0.95
            mock_dl.return_value = [mock_result]

            code, is_en = _detect_with_langdetect("Hola mundo", 0.9)
            assert code == "es"
            assert is_en is False

    def test_english_low_confidence_fails_open(self) -> None:
        """English below threshold should fail open."""
        with patch("app.pipeline.language.detect_langs") as mock_dl:
            mock_result = MagicMock()
            mock_result.lang = "en"
            mock_result.prob = 0.5  # below 0.9 threshold
            mock_dl.return_value = [mock_result]

            code, is_en = _detect_with_langdetect("Some text", 0.9)
            assert code == "unknown"
            assert is_en is False

    def test_langdetect_exception_fails_open(self) -> None:
        """langdetect exception should fail open."""
        from langdetect.lang_detect_exception import LangDetectException

        with patch(
            "app.pipeline.language.detect_langs",
            side_effect=LangDetectException(0, "error"),
        ):
            code, is_en = _detect_with_langdetect("test", 0.9)
            assert code == "unknown"
            assert is_en is False

    def test_empty_results_fails_open(self) -> None:
        """Empty results list should fail open."""
        with patch("app.pipeline.language.detect_langs", return_value=[]):
            code, is_en = _detect_with_langdetect("test", 0.9)
            assert code == "unknown"
            assert is_en is False


# ---------------------------------------------------------------------------
# detect_language (main entry point)
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    def test_non_latin_script_proceeds_to_translation(self) -> None:
        """Non-Latin script should return unknown/not-english (proceed to translation)."""
        image = _make_test_image()
        blocks = _make_blocks(["مرحبا"])
        settings = _create_test_settings()

        with patch(
            "app.pipeline.language.pytesseract.image_to_osd",
            return_value="Script: Arabic\nScript confidence: 1.0",
        ):
            result = detect_language(image, blocks, settings)
            assert result.language_code == "unknown"
            assert result.is_english is False

    def test_latin_english_returns_early(self) -> None:
        """Latin script + English langdetect → early return."""
        image = _make_test_image()
        blocks = _make_blocks(["Hello world this is English text"])
        settings = _create_test_settings()

        with patch(
            "app.pipeline.language.pytesseract.image_to_osd",
            return_value="Script: Latin\nScript confidence: 1.0",
        ):
            with patch("app.pipeline.language.detect_langs") as mock_dl:
                mock_result = MagicMock()
                mock_result.lang = "en"
                mock_result.prob = 0.95
                mock_dl.return_value = [mock_result]

                result = detect_language(image, blocks, settings)
                assert result.language_code == "en"
                assert result.is_english is True

    def test_latin_spanish_proceeds_to_translation(self) -> None:
        """Latin script + Spanish langdetect → proceed to translation."""
        image = _make_test_image()
        blocks = _make_blocks(["Oferta especial aceite de oliva"])
        settings = _create_test_settings()

        with patch(
            "app.pipeline.language.pytesseract.image_to_osd",
            return_value="Script: Latin\nScript confidence: 1.0",
        ):
            with patch("app.pipeline.language.detect_langs") as mock_dl:
                mock_result = MagicMock()
                mock_result.lang = "es"
                mock_result.prob = 0.95
                mock_dl.return_value = [mock_result]

                result = detect_language(image, blocks, settings)
                assert result.language_code == "es"
                assert result.is_english is False

    def test_osd_failure_fails_open(self) -> None:
        """OSD failure should fail open (proceed to translation)."""
        image = _make_test_image()
        blocks = _make_blocks(["Test"])
        settings = _create_test_settings()

        with patch(
            "app.pipeline.language.pytesseract.image_to_osd",
            side_effect=Exception("OSD failed"),
        ):
            result = detect_language(image, blocks, settings)
            assert result.language_code == "unknown"
            assert result.is_english is False

    def test_langdetect_failure_fails_open(self) -> None:
        """langdetect failure on Latin text should fail open."""
        image = _make_test_image()
        blocks = _make_blocks(["Some text"])
        settings = _create_test_settings()

        with patch(
            "app.pipeline.language.pytesseract.image_to_osd",
            return_value="Script: Latin\nScript confidence: 1.0",
        ):
            with patch(
                "app.pipeline.language.detect_langs",
                side_effect=Exception("langdetect crash"),
            ):
                result = detect_language(image, blocks, settings)
                assert result.language_code == "unknown"
                assert result.is_english is False

    def test_empty_blocks_fails_open(self) -> None:
        """Empty blocks list should fail open (no text to detect)."""
        image = _make_test_image()
        blocks: list[TextBlock] = []
        settings = _create_test_settings()

        with patch(
            "app.pipeline.language.pytesseract.image_to_osd",
            return_value="Script: Latin\nScript confidence: 1.0",
        ):
            result = detect_language(image, blocks, settings)
            assert result.language_code == "unknown"
            assert result.is_english is False

    def test_low_langdetect_confidence_fails_open(self) -> None:
        """Low langdetect confidence should fail open."""
        image = _make_test_image()
        blocks = _make_blocks(["Ambiguous text"])
        settings = _create_test_settings(LANGDETECT_MIN_CONFIDENCE=0.9)

        with patch(
            "app.pipeline.language.pytesseract.image_to_osd",
            return_value="Script: Latin\nScript confidence: 1.0",
        ):
            with patch("app.pipeline.language.detect_langs") as mock_dl:
                mock_result = MagicMock()
                mock_result.lang = "en"
                mock_result.prob = 0.4  # well below 0.9
                mock_dl.return_value = [mock_result]

                result = detect_language(image, blocks, settings)
                assert result.language_code == "unknown"
                assert result.is_english is False
