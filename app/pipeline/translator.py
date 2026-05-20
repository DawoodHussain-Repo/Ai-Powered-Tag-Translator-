from __future__ import annotations

import json

import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

from app.config import Settings
from app.exceptions import TranslationError
from app.models.schemas import TextBlock, TranslatedBlock


def _build_translation_prompt(
    blocks: list[TextBlock],
    source_language: str,
    retry: bool = False,
) -> str:
    """Build the batch translation prompt for Gemini.

    All blocks are sent in a single numbered list.  The prompt instructs
    Gemini to return a JSON array of translated strings in the same order.

    If ``retry`` is True, the prompt is made more explicit to encourage
    a better translation on the second attempt.
    """
    lines = [f"{i + 1}. {block.text}" for i, block in enumerate(blocks)]
    numbered_list = "\n".join(lines)

    base_instruction = (
        f"Translate the following {source_language} text items to English. "
        "Return ONLY a JSON array of translated strings in the same order. "
        "No explanations, no preamble, no markdown formatting — just the "
        "raw JSON array."
    )

    if retry:
        base_instruction += (
            "\n\nIMPORTANT: The previous translation attempt failed "
            "verification. Please ensure EVERY item is translated to "
            "clear, natural English. Do not leave any text untranslated."
        )

    return f"{base_instruction}\n\n{numbered_list}"


def _parse_translation_response(
    response_text: str,
    expected_count: int,
) -> list[str]:
    """Parse the Gemini response as a JSON array of strings.

    Raises ``TranslationError`` if the response cannot be parsed or
    the number of translations does not match the expected count.
    """
    # Strip any markdown code fencing Gemini might add
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        # Remove opening ```json or ``` and closing ```
        lines = cleaned.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise TranslationError(
            f"Failed to parse Gemini response as JSON: {exc}. "
            f"Raw response: {response_text[:200]}"
        ) from exc

    if not isinstance(parsed, list):
        raise TranslationError(
            f"Expected a JSON array, got {type(parsed).__name__}"
        )

    if len(parsed) != expected_count:
        raise TranslationError(
            f"Expected {expected_count} translations, got {len(parsed)}"
        )

    return [str(item) for item in parsed]


def translate_blocks(
    blocks: list[TextBlock],
    source_language: str,
    settings: Settings,
    retry: bool = False,
) -> list[TranslatedBlock]:
    """Translate all text blocks to English via the Gemini API.

    This is the main entry point for Node 4.  It sends all blocks in a
    single API call (batch prompt) and maps the translated strings back
    to ``TranslatedBlock`` objects preserving the original bounding boxes.

    Args:
        blocks: Text blocks extracted by the OCR step.
        source_language: ISO 639-1 code of the detected source language.
        settings: Application settings (API key, model name).
        retry: If True, uses a more explicit prompt for the retry attempt.

    Returns:
        A list of ``TranslatedBlock`` objects in the same order as input.

    Raises:
        TranslationError: If the Gemini API call fails or the response
            cannot be parsed.
    """
    if not blocks:
        return []

    prompt = _build_translation_prompt(blocks, source_language, retry=retry)

    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(settings.GEMINI_MODEL)
        response = model.generate_content(prompt)
        response_text = response.text
    except google_exceptions.GoogleAPIError as exc:
        raise TranslationError(
            f"Gemini API call failed: {exc}"
        ) from exc
    except Exception as exc:
        raise TranslationError(
            f"Unexpected error calling Gemini API: {exc}"
        ) from exc

    translations = _parse_translation_response(response_text, len(blocks))

    return [
        TranslatedBlock(
            original_text=block.text,
            translated_text=translated,
            bbox=block.bbox,
        )
        for block, translated in zip(blocks, translations)
    ]
