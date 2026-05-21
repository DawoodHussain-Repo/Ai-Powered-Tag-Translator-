# Image Text Translation Pipeline

## Overview

A stateless REST API that accepts a product image containing text in a foreign language
and returns a version of that image with all detected text replaced by its English
translation. The layout, visual content, and composition of the original image are
preserved — only the text regions change. Built as a prototype for a B2B e-commerce
platform where vendors upload packaging or promotional images in non-English languages.

## Goals

1. Accept any image (JPEG, PNG, WEBP) via a single POST endpoint and return a
   translated version with no additional UI or deployment required
2. Handle any source language — no hard-coded assumptions for Spanish or any other
   single language
3. Preserve the visual layout of the original image as closely as possible — the
   translated text must appear at the same positions and approximate size as the original

## Core User Flow

1. Client POSTs a multipart/form-data request with the image file to
   `POST /api/v1/translate-image`
2. API validates the file (type, size, openable)
3. API preprocesses the image — samples border pixel brightness and applies adaptive
   thresholding or inversion for dark-background images to recover white-on-dark text
4. API runs OCR on the preprocessed image and extracts all text blocks with their
   bounding boxes
5. API runs script detection (pytesseract OSD) on the preprocessed image; for
   Latin-script results, langdetect runs on the OCR text to identify the language
6. If the text is detected as English with sufficient confidence, the original image
   is returned immediately with status=already_english and no Gemini call is made
7. API sends extracted text to Gemini for English translation (per block)
8. API composites the output: fills original text bounding boxes with sampled background
   color, then draws translated text at the same positions using Pillow
9. API runs a verification pass (re-OCR on the output image) to confirm English text
   is now present
10. API returns the output image as base64 with metadata (source language, blocks
    translated, verification result)

## Features

### Core Pipeline

- Image validation: extension allowlist, MIME type sniffing, file size cap, PIL open check
- Image preprocessing: border pixel brightness sampling; adaptive threshold/invert
  applied to dark-background images before OCR to recover white-on-dark text
- OCR extraction: pytesseract `image_to_data()` for word/block-level text with bounding boxes
- Script detection: pytesseract OSD on preprocessed image determines script family
- Language detection: langdetect on concatenated OCR text, only for Latin-script images;
  fails open on low confidence or errors
- Early return: if OSD returns Latin script AND langdetect detects English with
  confidence ≥ LANGDETECT_MIN_CONFIDENCE, return original image with no Gemini call
- Translation: Gemini API (gemini-1.5-flash) via text-only prompt — one call per text block
  or batched blocks per image
- Image compositing: Pillow fills each bounding box with a sampled background color,
  then draws translated text with auto-scaled font to fit the bounding box
- Output verification: re-OCR of the composited image; heuristic presence check
  confirms non-empty alphabetic text; if check fails, one retry of translation and
  compositing before returning 200 with partial output and status=verification_failed
- Structured JSON response with base64 output image, source language, per-block metadata,
  and verification status

### Error Handling

- 400 on invalid file type, corrupt image, or file too large
- 200 with original image and `status: no_text_found` if OCR finds nothing
- 200 with original image and `status: already_english` if OSD returns Latin script
  and langdetect detects English with sufficient confidence — no Gemini call made
- 500 with error code if Gemini call fails or compositing fails after retry

## Scope

### In Scope

- Single image per request
- Any language readable by Tesseract; source language identification via OSD +
  langdetect for the English early-return path only; translation handled by Gemini
  without requiring source language to be known
- JPEG, PNG, and WEBP input formats
- Returning the output as base64 in a JSON response body
- Local execution only — no hosting or deployment

### Out of Scope

- Batch processing of multiple images in one request
- Preserving custom fonts (output uses a bundled open font, not the original typeface)
- Complex overlapping or rotated text blocks (vertical text, curved text)
- Authenticated endpoints or per-user rate limiting
- Persistent storage of input or output images
- Frontend UI

## Success Criteria

1. A POST request with a Spanish-language product image returns a 200 with a correctly
   translated output image where the original text positions are visually preserved
2. A POST request with an already-English image returns a 200 with the original image
   and `status: already_english` — OSD confirms Latin script, langdetect confirms
   English, and no Gemini call is made
3. A POST request with a non-image file returns a 400 with a clear error code
4. The pipeline handles at least the provided sample image set without errors
5. `README.md` covers how to run locally, an example curl request, and known limitations
