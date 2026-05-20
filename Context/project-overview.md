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
3. API runs OCR on the image and extracts all text blocks with their bounding boxes
4. API detects the source language of the extracted text
5. If the image is already in English, the original image is returned immediately
   with a flag indicating no translation was needed
6. API sends extracted text to Gemini for English translation (per block)
7. API composites the output: fills original text bounding boxes with sampled background
   color, then draws translated text at the same positions using Pillow
8. API runs a verification pass (re-OCR on the output image) to confirm English text
   is now present
9. API returns the output image as base64 with metadata (source language, blocks
   translated, verification result)

## Features

### Core Pipeline

- Image validation: extension allowlist, MIME type sniffing, file size cap, PIL open check
- OCR extraction: pytesseract `image_to_data()` for word/block-level text with bounding boxes
- Language detection: langdetect on concatenated OCR text
- Early return: if already English, skip all AI calls and return the original
- Translation: Gemini API (gemini-1.5-flash) via text-only prompt — one call per text block
  or batched blocks per image
- Image compositing: Pillow fills each bounding box with a sampled background color,
  then draws translated text with auto-scaled font to fit the bounding box
- Output verification: re-OCR of the composited image; if English is not detected, one
  retry of steps 4–5 before returning a 500 with partial output
- Structured JSON response with base64 output image, source language, per-block metadata,
  and verification status

### Error Handling

- 400 on invalid file type, corrupt image, or file too large
- 200 with original image and `status: no_text_found` if OCR finds nothing
- 200 with original image and `status: already_english` if source language is English
- 500 with error code if Gemini call fails or compositing fails after retry

## Scope

### In Scope

- Single image per request
- Languages detectable by langdetect and readable by Tesseract
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
   and `status: already_english` — no Gemini call is made
3. A POST request with a non-image file returns a 400 with a clear error code
4. The pipeline handles at least the provided sample image set without errors
5. `README.md` covers how to run locally, an example curl request, and known limitations
