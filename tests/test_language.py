from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.schemas import TextBlock
from app.pipeline.language import detect_language, is_english


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _block(text: str) -> TextBlock:
    """Create a TextBlock with dummy bbox/confidence for testing."""
    return TextBlock(text=text, bbox=(0, 0, 100, 20), confidence=90.0)


# ---------------------------------------------------------------------------
# detect_language
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    def test_detects_english(self) -> None:
        blocks = [_block("This is a simple English sentence for testing purposes")]
        result = detect_language(blocks)
        assert result == "en"

    def test_detects_spanish(self) -> None:
        blocks = [_block("Esta es una oración en español para pruebas")]
        result = detect_language(blocks)
        assert result == "es"

    def test_detects_french(self) -> None:
        blocks = [_block("Ceci est une phrase en français pour les tests")]
        result = detect_language(blocks)
        assert result == "fr"

    def test_multiple_blocks_concatenated(self) -> None:
        """Language detection works across multiple blocks concatenated."""
        blocks = [
            _block("Hola"),
            _block("esta es una prueba"),
            _block("en español"),
        ]
        result = detect_language(blocks)
        assert result == "es"

    def test_empty_blocks_returns_unknown(self) -> None:
        result = detect_language([])
        assert result == "unknown"

    def test_whitespace_only_blocks_returns_unknown(self) -> None:
        blocks = [_block("   "), _block("  ")]
        result = detect_language(blocks)
        assert result == "unknown"

    def test_langdetect_failure_returns_unknown(self) -> None:
        """If langdetect raises, return 'unknown' instead of crashing."""
        blocks = [_block("abc")]
        with patch(
            "app.pipeline.language.detect",
            side_effect=Exception("detection failed"),
        ):
            result = detect_language(blocks)
            assert result == "unknown"


# ---------------------------------------------------------------------------
# is_english
# ---------------------------------------------------------------------------

class TestIsEnglish:
    def test_en_is_english(self) -> None:
        assert is_english("en") is True

    def test_es_is_not_english(self) -> None:
        assert is_english("es") is False

    def test_unknown_is_not_english(self) -> None:
        assert is_english("unknown") is False

    def test_empty_string_is_not_english(self) -> None:
        assert is_english("") is False

    def test_en_us_is_not_english(self) -> None:
        """Only exact 'en' match; 'en-us' should not match."""
        assert is_english("en-us") is False
