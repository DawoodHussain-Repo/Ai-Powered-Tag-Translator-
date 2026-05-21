# Code Standards

## General

- Keep each module small and single-purpose — one pipeline node per file
- Fix root causes; do not add workarounds or try/except blocks that silently swallow errors
- Do not mix pipeline logic with HTTP concerns — route handlers orchestrate, pipeline
  modules execute
- Prefer explicit over implicit — no magic, no monkey-patching, no global mutable state
- All configuration comes from `app/config.py` via pydantic-settings — no hardcoded
  values anywhere in the codebase (no hardcoded language codes, no hardcoded file size
  numbers, no hardcoded Gemini model strings)

## Python

- Python 3.11+ required; use `match` statements for exhaustive status handling
- Strict type annotations on all function signatures — no bare `Any`, use `Union` or
  `Optional` with explicit types
- Use `from __future__ import annotations` in every module for forward reference support
- Validate all external inputs at system boundaries using Pydantic models before any
  logic runs — this applies to the incoming HTTP request AND to Gemini API responses
- Never log the image payload, base64 strings, or the GEMINI_API_KEY
- Raise domain-specific exceptions (`ValidationError`, `OCRError`, `TranslationError`,
  `CompositorError`) from pipeline nodes — never raise raw `Exception` or `ValueError`
  from a node
- The route handler catches domain exceptions and maps them to HTTP responses

## FastAPI

- One route file for the prototype (`app/api/routes.py`) with one handler
- The route handler is the only place that imports and calls pipeline nodes in sequence
- Use `UploadFile` + `File(...)` for the image input — do not accept base64 in the
  request body (multipart is the correct contract for binary file upload)
- Use `Response(content=..., media_type="application/json")` for error responses so
  the status code is always explicit
- All responses must match the schema defined in `app/models/` — no ad-hoc dicts
  returned from handlers
- Request validation (file extension, content-type header) is done in the route handler
  before passing to the pipeline; pipeline nodes assume the input is a valid open PIL Image

## Pydantic Models

- Define one Pydantic model per data shape: `TextBlock`, `TranslatedBlock`,
  `PipelineResult`, `ErrorResponse`
- `TextBlock`: `text: str`, `bbox: tuple[int, int, int, int]`, `confidence: float`
- `TranslatedBlock`: `original_text: str`, `translated_text: str`,
  `bbox: tuple[int, int, int, int]`
- `PipelineResult`: `status: Literal["translated","already_english","no_text_found",
  "verification_failed"]`, `source_language: str | None`, `blocks_translated: int`,
  `output_image: str`, `output_format: Literal["jpeg"]`
- `ErrorResponse`: `error: str`, `code: str`
- All models use `model_config = ConfigDict(frozen=True)` — pipeline data is immutable

## OCR / Text Extraction (OCRExtractor node)

- Bounding box filtering: filter out single non-alphanumeric characters or blocks with a bounding box area (w * h) below `MIN_BBOX_AREA` to avoid rendering noise artifacts.
- Filter out blocks that do not meet the minimum confidence threshold (`MIN_OCR_CONFIDENCE`).

## Gemini API (TextTranslator node)

- Always use `gemini-1.5-flash` — never hardcode another model; read from config
- Send all text blocks in a single API call per image (batch prompt) to minimize
  quota usage
- Prompt must specify: return a JSON array of translated strings in the same order as
  input, no explanations, no preamble, just the JSON array
- Parse the response as JSON immediately; if parse fails, raise `TranslationError`
- Do not send the image to Gemini — send extracted text strings only; Gemini is used
  purely for text-to-text translation
- Wrap the Gemini call in a try/except that catches `google.api_core.exceptions` and
  re-raises as `TranslationError` with the original message preserved

## Pillow / Image Compositing

- Always work on `image.copy()` — never mutate the original PIL Image passed into
  the compositor
- Background color sampling: take a 5-pixel border around each bounding box and use
  the median pixel value — do not assume white or any fixed background color
- Foreground color sampling: sample pixels within the original bbox before erasure
  and use the median dark pixel value as the text color
- Font auto-scaling: start from the bbox height as the initial font size, reduce in
  steps of 1pt until the rendered text width fits within bbox width minus 2px padding
- Minimum font size: 8pt — if text cannot fit, truncate with ellipsis rather than
  rendering 0pt or negative size
- Clamp all bbox coordinates to `(0, 0, image.width, image.height)` before any draw call
- Use `NotoSans-Regular.ttf` from `assets/fonts/` — this font must be checked into the
  repository, not downloaded at runtime

## API Contract

- Method: `POST`
- Path: `/api/v1/translate-image`
- Content-Type: `multipart/form-data`
- Field name: `file` (the image)
- Success response: `200 application/json` with `PipelineResult` schema
- Client error response: `400 application/json` with `ErrorResponse` schema
- Server error response: `500 application/json` with `ErrorResponse` schema
- Error codes (the `code` field): `INVALID_FILE_TYPE`, `INVALID_FILE_SIZE`,
  `CORRUPT_IMAGE`, `TRANSLATION_FAILED`, `COMPOSITOR_FAILED`, `INTERNAL_ERROR`

## File Organization

- `app/` — all application source code
- `app/main.py` — FastAPI app factory only; no business logic
- `app/api/routes.py` — route handler(s); pipeline orchestration only
- `app/pipeline/` — one file per pipeline node (`validator.py`, `preprocessor.py`, `ocr.py`, `language.py`, `translator.py`, `compositor.py`, `verifier.py`, `serializer.py`); no cross-node imports
- `app/models/` — Pydantic data models only; no logic
- `app/config.py` — pydantic-settings Config; no logic
- `assets/fonts/` — bundled font files checked into git
- `tests/` — pytest tests mirroring the `app/` structure
- `samples/` — provided sample images for local testing
- `.env.example` — template showing required env vars with no real values
- `README.md` — setup instructions, example curl, design decisions, limitations

## Environment Variables (defined in config.py)

- `GEMINI_API_KEY` — required; no default
- `MAX_FILE_SIZE_MB` — optional; default 10
- `MIN_OCR_CONFIDENCE` — optional; default 40 (0–100 scale from Tesseract)
- `MIN_BBOX_AREA` — optional; default 100 (in pixels²)
- `GEMINI_MODEL` — optional; default `gemini-1.5-flash`
