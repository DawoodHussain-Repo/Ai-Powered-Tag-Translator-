# AI Workflow Rules

## Approach

Build this project incrementally using a spec-driven workflow. The context files
(`project-overview.md`, `architecture.md`, `code-standards.md`) define what to build,
how to build it, and every constraint that applies. Always implement strictly against
these specs — do not infer or invent behavior that is not defined here. When the spec
is silent on something, add it as an open question before writing any code.

## Implementation Order

Work through the pipeline nodes in this exact sequence. Each unit must work end to end
before the next begins.

1. **Project scaffold** — FastAPI app factory, config, Pydantic models, folder structure,
   `NotoSans-Regular.ttf` in `assets/fonts/`, `.env.example`, basic health check route
2. **Node 1 — InputValidator** — file extension, MIME sniff, size cap, PIL open check;
   unit test with valid + invalid inputs
3. **Node 2 — ImagePreprocessor** — sample border pixels for median brightness, adaptive
   threshold/invert copy on dark backgrounds for OCR; unit test with dark/light backgrounds
4. **Node 3 — OCRExtractor** — pytesseract `image_to_data`, block grouping, confidence
   filter, noise filtering (non-alphanumeric, bbox area < MIN_BBOX_AREA); unit test against a known image with text
5. **Node 4 — LanguageDetector** — pytesseract OSD script detection on preprocessed image;
   if Latin script, langdetect on concatenated OCR text for English early-return;
   fail-open on any detection error; unit test covers: non-Latin script proceeds to
   translation, English Latin-script returns early, Spanish Latin-script proceeds to
   translation, langdetect failure proceeds to translation
6. **Node 5 — TextTranslator** — Gemini API batch prompt, JSON response parsing,
   TranslationError mapping; unit test with a mocked Gemini response
7. **Node 6 — ImageCompositor** — background sampling, bbox fill, font auto-scale,
   text draw, coordinate clamping; unit test confirms output differs from input only
   in text regions
8. **Node 7 — OutputVerifier** — re-OCR via pytesseract.image_to_string(), heuristic
   presence check (non-empty text with alphabetic tokens of length > 2), retry routing;
   unit test confirms retry is triggered exactly once on first failure and that empty
   OCR output triggers the fail path
9. **Node 8 — ResponseSerializer** — base64 encode, PipelineResult construction
10. **Route handler** — orchestrate all nodes; map domain exceptions to HTTP responses
11. **Integration test** — run the full pipeline against all provided sample images;
    verify output images visually and by re-OCR

## Scoping Rules

- Work on one node at a time — do not implement two nodes in the same step
- Do not add features not listed in `project-overview.md` (no batch processing, no auth,
  no frontend, no deployment config)
- Do not modify `app/models/` after unit 1 without updating `architecture.md` first
- The route handler is written last — it is a thin orchestrator that calls already-tested
  nodes; it should not contain any logic that belongs in a node

## When to Split Work

Split an implementation step if it combines:

- A pipeline node change and a Pydantic model change
- Gemini prompt logic and Pillow compositing logic
- Any two unrelated pipeline nodes in the same commit

If a change cannot be verified by a unit test or a single curl request quickly,
the scope is too broad — split it.

## Handling Missing Requirements

- Do not invent product behavior not defined in `project-overview.md` or `architecture.md`
- If a requirement is ambiguous (e.g. how to handle vertical text, mixed-language images,
  very small bounding boxes), add it as an open question in `progress-tracker.md` and
  implement the simpler, more conservative behavior until resolved
- Never hard-code assumptions that only hold for Spanish — any language-specific logic
  must be parameterized

## Protected Files

Do not modify the following unless explicitly instructed:

- `assets/fonts/NotoSans-Regular.ttf` — checked-in font binary; do not replace or remove
- `app/models/` — Pydantic models are finalized in unit 1; changes require explicit
  instruction and a matching update to `architecture.md`
- `.env.example` — only add new keys when a new env var is added to `app/config.py`

## Gemini API Rules

- Never send the image binary or base64 to Gemini — send extracted text strings only
- Gemini is used for text-to-text translation exclusively; never for image generation,
  image analysis, or OCR
- Always batch all blocks into a single Gemini call per image
- Always parse the Gemini response as JSON; if parsing fails, raise `TranslationError`
  immediately — do not attempt string parsing or regex fallback

## Keeping Docs in Sync

Update the relevant context file whenever implementation reveals a gap or change:

- A new pipeline node or step is added → update `architecture.md` Pipeline Nodes section
- A new environment variable is needed → update `code-standards.md` and `.env.example`
- A known limitation is discovered → add it to the Limitations section of `README.md`
- A Pydantic model field changes → update `architecture.md` Pydantic Models section
  in `code-standards.md`

## Before Moving to the Next Unit

1. The current node works end to end within its defined scope (unit test passes)
2. No invariant defined in `architecture.md` was violated (check the invariants list)
3. `progress-tracker.md` is updated with the completed node and any open questions
4. The node does not import any other pipeline node directly
5. `uvicorn app.main:app --reload` starts without errors after the change
