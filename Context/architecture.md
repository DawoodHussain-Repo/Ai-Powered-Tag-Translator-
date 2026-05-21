# Architecture Context

## Stack

| Layer          | Technology                        | Role                                                       |
| -------------- | --------------------------------- | ---------------------------------------------------------- |
| Framework      | FastAPI + Python 3.11+            | REST API server, request lifecycle, error handling         |
| OCR            | pytesseract (Tesseract 5.x)       | Text extraction with bounding boxes from images            |
| Lang. Det.     | pytesseract OSD + langdetect      | Script detection (OSD) and English early-return (langdetect) |
| Translation    | Gemini API (gemini-1.5-flash)     | Text-only translation of OCR-extracted blocks to English   |
| Compositing    | Pillow (PIL)                      | Erase original text regions, draw translated text          |
| Font Rendering | Pillow ImageFont + bundled TTF    | Auto-scaled text rendering at original bounding box coords |
| Config         | python-dotenv + pydantic-settings | Environment variable management (GEMINI_API_KEY, etc.)     |
| Dev Server     | uvicorn                           | Local ASGI server for running the API                      |

## Pipeline Nodes

The pipeline is a linear sequence of discrete, single-responsibility steps.
Each step receives the output of the previous step and passes its output forward.
Steps 5–6 can be retried once if the output verification step fails.

```
POST /api/v1/translate-image (multipart/form-data: file)
        │
        ▼
[Node 1] InputValidator
        │  Checks: file extension allowlist (jpg, jpeg, png, webp)
        │  Checks: MIME type sniffing (python-magic or imghdr)
        │  Checks: file size ≤ MAX_FILE_SIZE_MB (default 10 MB)
        │  Checks: PIL.Image.open() succeeds (not corrupt)
        │  Output: PIL Image object
        │  Failure: raises ValidationError → 400 + error code
        │
        ▼
[Node 2] ImagePreprocessor
        │  Method: Sample border pixels of the image, compute median brightness
        │  Dark background: If median brightness < 128, produce an adaptive-thresholded
        │                  or inverted copy of the image to serve as the OCR input
        │  Light background: Pass through the original image unchanged
        │  Output: PIL Image (either original or preprocessed for OCR only)
        │  Invariant: Preprocessed image is only used for OCRExtractor and LanguageDetector;
        │             original unmodified image is always passed to downstream compositor
        │
        ▼
[Node 3] OCRExtractor
        │  Tool: pytesseract.image_to_data(preprocessed_image, output_type=Output.DICT)
        │  Extracts: text, confidence, left, top, width, height per word
        │  Groups: consecutive words into block-level text chunks
        │           (group by block_num + par_num + line_num from tesseract output)
        │  Filters: confidence threshold ≥ MIN_OCR_CONFIDENCE (default 40)
        │           and filters out noise (single non-alphanumeric char or bbox area < MIN_BBOX_AREA)
        │  Output: list of TextBlock { text, bbox: (x,y,w,h), confidence }
        │  No text found: return 200 + original image + status=no_text_found
        │
        ▼
[Node 4] LanguageDetector
        │  Step 1 — pytesseract.image_to_osd(preprocessed_image)
        │    Extracts: detected script (e.g. "Latin", "Arabic", "Han", "Cyrillic")
        │    If non-Latin script: proceed directly to Node 5 — no further detection needed
        │  Step 2 — langdetect.detect() on concatenated OCR text from Node 3
        │    Only reached when script is Latin (covers Spanish, English, French, etc.)
        │    If detected language == "en": early return → 200 + original image +
        │                                  status=already_english (no Gemini call made)
        │    If detected language != "en": proceed to Node 5
        │    If langdetect raises / confidence too low: fail open → proceed to Node 5
        │  Output: language code string (e.g. "es", "en", "fr") or "unknown"
        │  Failure: fails open — any detection error proceeds to Node 5, never blocks pipeline
        │
        ▼
[Node 5] TextTranslator                             ◄─── retry point
        │  Tool: Gemini API gemini-1.5-flash
        │  Strategy: batch all blocks into a single prompt to minimize API calls
        │  Prompt format: numbered list of source text strings
        │  Response format: JSON array of translated strings (same order/count)
        │  Maps: translated string back to each TextBlock by index
        │  Output: list of TranslatedBlock { original_text, translated_text, bbox }
        │  Failure: raises TranslationError → 500 (or retry trigger from Node 7)
        │
        ▼
[Node 6] ImageCompositor                            ◄─── retry point
        │  Step A — Erase original text:
        │    For each bbox, sample background color from a 5px border around the bbox
        │    Fill the bbox region with the sampled color using PIL ImageDraw.rectangle()
        │    Apply slight gaussian blur to the filled region to reduce hard edges
        │  Step B — Render translated text:
        │    For each bbox, auto-scale font size to fit translated text within bbox width
        │    Use a bundled Unicode TTF (e.g. NotoSans-Regular) for broad language support
        │    Draw text with PIL ImageDraw.text() at the bbox (x, y) origin
        │    Foreground color: sampled from the original text pixels before erasure
        │  Output: PIL Image (composited)
        │  Failure: raises CompositorError → 500
        │
        ▼
[Node 7] OutputVerifier
        │  Tool: pytesseract.image_to_string() on composited image
        │  Check: re-OCR'd text is non-empty AND contains at least one alphabetic token
        │         of length > 2 (heuristic presence check — not language classification)
        │  Pass: check passes → proceed to Node 8
        │  Fail (first time): route back to Node 5 with retry_count=1 and
        │                      an adjusted prompt (more explicit translation instruction)
        │  Fail (second time): return 200 with partial output + status=verification_failed
        │                       (do not 500 — partial output is still useful)
        │
        ▼
[Node 8] ResponseSerializer
           Encodes composited image as base64 (JPEG, quality=90)
           Builds JSON response:
             {
               "status": "translated" | "already_english" | "no_text_found" | "verification_failed",
               "source_language": "es",
               "blocks_translated": 4,
               "output_image": "<base64>",
               "output_format": "jpeg"
             }
```

## System Boundaries

- `app/main.py` — FastAPI application factory, route registration, lifespan hooks
- `app/api/routes.py` — Single route handler for POST /api/v1/translate-image;
  orchestrates the pipeline by calling each node in order
- `app/pipeline/` — One module per pipeline node; no node imports another node directly
- `app/pipeline/validator.py` — Node 1: InputValidator
- `app/pipeline/preprocessor.py` — Node 2: ImagePreprocessor
- `app/pipeline/ocr.py` — Node 3: OCRExtractor
- `app/pipeline/language.py` — Node 4: LanguageDetector
- `app/pipeline/translator.py` — Node 5: TextTranslator (Gemini API client)
- `app/pipeline/compositor.py` — Node 6: ImageCompositor (Pillow logic)
- `app/pipeline/verifier.py` — Node 7: OutputVerifier
- `app/pipeline/serializer.py` — Node 8: ResponseSerializer
- `app/models/` — Pydantic models for TextBlock, TranslatedBlock, PipelineResult, ErrorResponse
- `app/config.py` — pydantic-settings Config class (GEMINI_API_KEY, MAX_FILE_SIZE_MB, etc.)
- `assets/fonts/` — Bundled NotoSans-Regular.ttf (covers Latin, CJK subset, Arabic subset)
- `tests/` — pytest unit tests per pipeline node + integration test against sample images

## Storage Model

- **No persistent storage.** The pipeline is fully stateless.
- Input images are held in memory as PIL Image objects for the duration of the request.
- Output images are encoded to base64 in memory and returned in the response body.
- No files are written to disk during normal operation.

## Auth and Access Model

- No authentication on the prototype. The endpoint is open.
- The GEMINI_API_KEY is loaded from `.env` via pydantic-settings and is never logged
  or returned in any response.
- Rate limiting is out of scope for the prototype.

## Invariants

1. **The original image is never mutated.** All compositing operates on a `.copy()` of
   the PIL Image object. The original is preserved for early-return paths and for
   sampling background/foreground colors.
2. **Gemini is called only for text translation, never for image generation.**
   The output image is always derived from the original via Pillow compositing — never
   AI-generated or regenerated.
3. **Language detection uses OSD for script and langdetect for Latin-script languages.**
   pytesseract OSD determines the script family. For non-Latin scripts, the pipeline
   proceeds directly to translation. For Latin-script text, langdetect.detect() is run
   on the concatenated OCR output to identify the language. If langdetect detects English,
   the pipeline returns early with no Gemini call. If langdetect fails or is uncertain,
   the pipeline proceeds to translation (fail open). langdetect is never the sole blocker.
4. **Each pipeline node has a single responsibility.** No node performs two pipeline
   steps. The route handler in `routes.py` is the only place that knows the node order.
5. **No background tasks or async work is spawned inside a request handler.**
   The pipeline runs synchronously within the request. The endpoint is blocking.
   (Acceptable for a prototype; production would use a task queue.)
6. **Bounding box coordinates are always validated before compositing.**
   Coordinates are clamped to image dimensions before any PIL draw call to prevent
   out-of-bounds errors on edge-case OCR results.
7. **The preprocessed image is used only by OCRExtractor and LanguageDetector, never by ImageCompositor or downstream nodes.**
   To ensure the visual layout and content of the original image are preserved, any
   adaptive-thresholded or inverted copy created for improving OCR quality must be kept isolated
   to the extraction/detection phases. The original unmodified image is always passed to the compositor.
