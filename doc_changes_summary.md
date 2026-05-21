# Summary of Documentation Changes

This document details the modifications made to the project markdown files (`.md`) to align them precisely with the final, verified codebase implementation.

---

## 1. Context/code-standards.md

- **Foreground Color Sampling (Lines 91-93)**:
  - **Before**: Described foreground color sampling as using only the median dark pixel value.
  - **After**: Updated to describe the contrast-aware text color sampling. If the background is dark (luminance < 128), it uses the median of the lightest pixels. If the background is light, it uses the median of the darkest pixels.
- **File Organization (Line 123)**:
  - **Before**: Referenced the samples directory as `samples/`.
  - **After**: Updated to match the actual folder name `sample_images_for_candidates/`.

---

## 2. Context/architecture.md

- **OutputVerifier Tooling (Lines 94-96)**:
  - **Before**: Described Node 7 (`OutputVerifier`) as running OCR on the raw composited image.
  - **After**: Updated to clarify that Node 7 runs on the preprocessed composited image (inverted if dark background) to ensure light-on-dark text is correctly verified.
- **Invariant 7 (Lines 172-177)**:
  - **Before**: Stated that the preprocessed image is never used by downstream nodes.
  - **After**: Clarified that while the input preprocessed image is kept isolated from the compositor, the `OutputVerifier` uses a newly preprocessed version of the composited output image.
- **ImagePreprocessor References (Lines 37-38, 172-177)**:
  - **Before**: Referred to the preprocessor output as an "adaptive-thresholded or inverted" copy.
  - **After**: Removed mentions of "adaptive-thresholded" to accurately reflect that only global color inversion is implemented.

---

## 3. Context/project-overview.md

- **Core User Flow Step 3 (Lines 25-26)**:
  - **Before**: Mentioned "adaptive thresholding or inversion" for dark-background preprocessing.
  - **After**: Updated to mention only "inverts the image" to align with the actual preprocessing implementation.
- **Core User Flow Step 9 (Lines 36-37)**:
  - **Before**: Described output verification running on the raw output image.
  - **After**: Updated to specify that it runs on the preprocessed/inverted version of the output image.
- **Features Section - Preprocessing (Lines 46-47)**:
  - **Before**: Referenced "adaptive threshold/invert".
  - **After**: Simplified to "inversion applied to dark-background images".
- **Features Section - Output Verification (Line 58)**:
  - **Before**: Specified re-OCR of the composited image.
  - **After**: Updated to specify re-OCR of the preprocessed/inverted version of the composited image.

---

## 4. Context/ai-workflow-rules.md

- **Node 2 Description (Lines 20-21)**:
  - **Before**: Mentioned "adaptive threshold/invert copy".
  - **After**: Simplified to "invert copy" to align with the actual preprocessor implementation.
- **Node 7 Description (Lines 34-35)**:
  - **Before**: Specified re-OCR on the raw composited image.
  - **After**: Updated to specify re-OCR on the preprocessed composited image (inverted if dark background).

---

## 5. README.md

- **Known Limitations (Line 60)**:
  - **Removed**: The item stating that the Latin-script English early-return was not implemented. The final implementation includes `langdetect`-based English early-return for Latin-script text, making this limitation obsolete.

---

## 6. progress-tracker.md

- **Node / Unit Statuses**:
  - Marked all nodes and units as `[x]` Completed.
  - Updated notes to reflect the completed state of the preprocessor, OCRExtractor noise filters, LanguageDetector OSD script detection, ImageCompositor text color sampling, and OutputVerifier preprocessing support.

---

## 7. Additional MD Updates (2026-05-22)

- **Context/architecture.md**:
  - Added a "Cleans" step to Node 3 OCRExtractor to strip leading/trailing non-alphanumeric characters and discard empty text blocks (Failure 1).
  - Explicitly updated the prompt format in Node 5 TextTranslator to instruct Gemini to translate every string without exception (Failure 2).
- **Context/code-standards.md**:
  - Documented the text-cleaning requirement under the OCR/Text Extraction section.
  - Documented the translation prompt requirement in the Gemini API section.
- **README.md**:
  - Added two new entries under "Known Limitations" covering *Graphical symbols rendered as text* and *Partial translations on English-resembling words* (Failure 3).

