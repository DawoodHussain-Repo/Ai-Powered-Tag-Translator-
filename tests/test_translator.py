from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.exceptions import TranslationError
from app.models.schemas import TextBlock, TranslatedBlock
from app.pipeline.translator import (
    _build_translation_prompt,
    _parse_translation_response,
    translate_blocks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_settings(**overrides: object) -> Settings:
    """Build a Settings instance with test defaults."""
    defaults = {
        "GEMINI_API_KEY": "test-key-not-real",
        "MAX_FILE_SIZE_MB": 10,
        "MIN_OCR_CONFIDENCE": 40,
        "GEMINI_MODEL": "gemini-1.5-flash",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _block(text: str) -> TextBlock:
    """Create a TextBlock with dummy bbox/confidence."""
    return TextBlock(text=text, bbox=(10, 20, 100, 30), confidence=90.0)


# ---------------------------------------------------------------------------
# _build_translation_prompt
# ---------------------------------------------------------------------------

class TestBuildTranslationPrompt:
    def test_basic_prompt(self) -> None:
        blocks = [_block("Hola"), _block("Mundo")]
        prompt = _build_translation_prompt(blocks, "es")
        assert "1. Hola" in prompt
        assert "2. Mundo" in prompt
        assert "JSON array" in prompt
        assert "es" in prompt

    def test_translation_instruction_in_prompt(self) -> None:
        blocks = [_block("Hola")]
        prompt = _build_translation_prompt(blocks, "es")
        assert "Translate every string to English without exception" in prompt
        assert "Do not leave any string unchanged" in prompt

    def test_retry_prompt_adds_emphasis(self) -> None:
        blocks = [_block("Hola")]
        prompt = _build_translation_prompt(blocks, "es", retry=True)
        assert "IMPORTANT" in prompt
        assert "previous translation attempt failed" in prompt

    def test_no_retry_has_no_emphasis(self) -> None:
        blocks = [_block("Hola")]
        prompt = _build_translation_prompt(blocks, "es", retry=False)
        assert "IMPORTANT" not in prompt


# ---------------------------------------------------------------------------
# _parse_translation_response
# ---------------------------------------------------------------------------

class TestParseTranslationResponse:
    def test_valid_json_array(self) -> None:
        result = _parse_translation_response('["Hello", "World"]', 2)
        assert result == ["Hello", "World"]

    def test_json_with_markdown_fencing(self) -> None:
        """Gemini sometimes wraps JSON in ```json ... ```."""
        response = '```json\n["Hello", "World"]\n```'
        result = _parse_translation_response(response, 2)
        assert result == ["Hello", "World"]

    def test_json_with_plain_fencing(self) -> None:
        response = '```\n["Hello"]\n```'
        result = _parse_translation_response(response, 1)
        assert result == ["Hello"]

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(TranslationError, match="Failed to parse"):
            _parse_translation_response("not json at all", 1)

    def test_non_array_raises(self) -> None:
        with pytest.raises(TranslationError, match="Expected a JSON array"):
            _parse_translation_response('{"key": "value"}', 1)

    def test_wrong_count_raises(self) -> None:
        with pytest.raises(TranslationError, match="Expected 3 translations"):
            _parse_translation_response('["Hello", "World"]', 3)

    def test_numeric_values_converted_to_strings(self) -> None:
        """Non-string values in the array should be stringified."""
        result = _parse_translation_response("[123, 456]", 2)
        assert result == ["123", "456"]


# ---------------------------------------------------------------------------
# translate_blocks (with mocked Gemini API)
# ---------------------------------------------------------------------------

class TestTranslateBlocks:
    def test_successful_translation(self) -> None:
        """Happy path: Gemini returns valid JSON array."""
        blocks = [_block("Hola"), _block("Mundo")]
        settings = _create_test_settings()

        mock_response = MagicMock()
        mock_response.text = '["Hello", "World"]'

        with patch("app.pipeline.translator.genai") as mock_genai:
            mock_model = MagicMock()
            mock_model.generate_content.return_value = mock_response
            mock_genai.GenerativeModel.return_value = mock_model

            result = translate_blocks(blocks, "es", settings)

        assert len(result) == 2
        assert isinstance(result[0], TranslatedBlock)
        assert result[0].original_text == "Hola"
        assert result[0].translated_text == "Hello"
        assert result[0].bbox == (10, 20, 100, 30)
        assert result[1].original_text == "Mundo"
        assert result[1].translated_text == "World"

    def test_empty_blocks_returns_empty(self) -> None:
        settings = _create_test_settings()
        result = translate_blocks([], "es", settings)
        assert result == []

    def test_retry_flag_passed_to_prompt(self) -> None:
        """Retry flag should produce a different prompt."""
        blocks = [_block("Hola")]
        settings = _create_test_settings()

        mock_response = MagicMock()
        mock_response.text = '["Hello"]'

        with patch("app.pipeline.translator.genai") as mock_genai:
            mock_model = MagicMock()
            mock_model.generate_content.return_value = mock_response
            mock_genai.GenerativeModel.return_value = mock_model

            translate_blocks(blocks, "es", settings, retry=True)

            call_args = mock_model.generate_content.call_args[0][0]
            assert "IMPORTANT" in call_args

    def test_api_failure_raises_translation_error(self) -> None:
        """Gemini API errors are wrapped in TranslationError."""
        from google.api_core.exceptions import GoogleAPIError

        blocks = [_block("Hola")]
        settings = _create_test_settings()

        with patch("app.pipeline.translator.genai") as mock_genai:
            mock_model = MagicMock()
            mock_model.generate_content.side_effect = GoogleAPIError(
                "quota exceeded"
            )
            mock_genai.GenerativeModel.return_value = mock_model

            with pytest.raises(TranslationError, match="Gemini API call failed"):
                translate_blocks(blocks, "es", settings)

    def test_parse_failure_raises_translation_error(self) -> None:
        """Invalid Gemini response raises TranslationError."""
        blocks = [_block("Hola")]
        settings = _create_test_settings()

        mock_response = MagicMock()
        mock_response.text = "not valid json"

        with patch("app.pipeline.translator.genai") as mock_genai:
            mock_model = MagicMock()
            mock_model.generate_content.return_value = mock_response
            mock_genai.GenerativeModel.return_value = mock_model

            with pytest.raises(TranslationError, match="Failed to parse"):
                translate_blocks(blocks, "es", settings)

    def test_preserves_bbox_from_input(self) -> None:
        """Bounding boxes from input blocks carry through to output."""
        block = TextBlock(
            text="Precio", bbox=(50, 100, 200, 40), confidence=95.0
        )
        settings = _create_test_settings()

        mock_response = MagicMock()
        mock_response.text = '["Price"]'

        with patch("app.pipeline.translator.genai") as mock_genai:
            mock_model = MagicMock()
            mock_model.generate_content.return_value = mock_response
            mock_genai.GenerativeModel.return_value = mock_model

            result = translate_blocks([block], "es", settings)

        assert result[0].bbox == (50, 100, 200, 40)

    def test_configures_api_key_from_settings(self) -> None:
        """The API key from settings is passed to genai.configure()."""
        blocks = [_block("Hola")]
        settings = _create_test_settings(GEMINI_API_KEY="my-secret-key")

        mock_response = MagicMock()
        mock_response.text = '["Hello"]'

        with patch("app.pipeline.translator.genai") as mock_genai:
            mock_model = MagicMock()
            mock_model.generate_content.return_value = mock_response
            mock_genai.GenerativeModel.return_value = mock_model

            translate_blocks(blocks, "es", settings)

            mock_genai.configure.assert_called_once_with(
                api_key="my-secret-key"
            )

    def test_uses_model_from_settings(self) -> None:
        """The model name from settings is used to create the model."""
        blocks = [_block("Hola")]
        settings = _create_test_settings(GEMINI_MODEL="gemini-1.5-pro")

        mock_response = MagicMock()
        mock_response.text = '["Hello"]'

        with patch("app.pipeline.translator.genai") as mock_genai:
            mock_model = MagicMock()
            mock_model.generate_content.return_value = mock_response
            mock_genai.GenerativeModel.return_value = mock_model

            translate_blocks(blocks, "es", settings)

            mock_genai.GenerativeModel.assert_called_once_with(
                "gemini-1.5-pro"
            )
