# Progress Tracker

This document tracks the implementation status of all pipeline nodes, workflow units, and outstanding design decisions/open questions.

## Pipeline Nodes Status

- `[x]` **Node 1: InputValidator** (Unit 2)
- `[x]` **Node 2: ImagePreprocessor** (Unit 3) - *Completed*
- `[x]` **Node 3: OCRExtractor** (Unit 4) - *Completed and updated with noise filtering and MIN_BBOX_AREA*
- `[x]` **Node 4: LanguageDetector** (Unit 5) - *Completed and updated with pytesseract OSD script detection*
- `[x]` **Node 5: TextTranslator** (Unit 6)
- `[x]` **Node 6: ImageCompositor** (Unit 7) - *Completed and updated for light-on-dark text sampling*
- `[x]` **Node 7: OutputVerifier** (Unit 8) - *Completed and updated with heuristic check and preprocessing support*
- `[x]` **Node 8: ResponseSerializer** (Unit 9)

## Workflow Units Status

- `[x]` **Unit 1: Project scaffold**
- `[x]` **Unit 2: Node 1 — InputValidator**
- `[x]` **Unit 3: Node 2 — ImagePreprocessor**
- `[x]` **Unit 4: Node 3 — OCRExtractor**
- `[x]` **Unit 5: Node 4 — LanguageDetector**
- `[x]` **Unit 6: Node 5 — TextTranslator**
- `[x]` **Unit 7: Node 6 — ImageCompositor**
- `[x]` **Unit 8: Node 7 — OutputVerifier**
- `[x]` **Unit 9: Node 8 — ResponseSerializer**
- `[x]` **Unit 10: Route handler**
- `[x]` **Unit 11: Integration test**

---

## Open Questions & Future Enhancements

### Per-region background preprocessing for mixed-background images
- **Problem**: Images (e.g. `02_aceite_oliva`) containing both dark headers (with light text) and light bodies (with dark text) fail when preprocessed globally.
- **Proposed Future Improvement**: Perform per-region background analysis and run adaptive preprocessing locally within each proposed text bounding box, rather than globally thresholding or inverting the entire image.

### Font weight inference and bold variant selection
- **Problem**: Headings and bold typography become standard weight in the rendered output, resulting in visual mismatch.
- **Proposed Future Improvement**: Analyze local pixel density or run stroke-width transform analysis within the bounding boxes to infer font weight and dynamically select matching font files (e.g., `NotoSans-Bold.ttf`, `NotoSans-Italic.ttf`).
