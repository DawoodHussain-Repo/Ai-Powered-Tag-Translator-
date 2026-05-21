from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps


def _sample_border_brightness(image: Image.Image, border_px: int = 10) -> float:
    """Sample border pixels and return the median brightness (0–255).

    Samples pixels from the top, bottom, left, and right edges of the
    image, each ``border_px`` pixels deep.  Converts to grayscale first
    so the result is a single brightness scalar.
    """
    gray = ImageOps.grayscale(image)
    arr = np.array(gray)

    h, w = arr.shape
    # Clamp border_px so it never exceeds half the image dimension
    bp = min(border_px, h // 2, w // 2, max(1, border_px))

    samples: list[np.ndarray] = []
    samples.append(arr[:bp, :].flatten())        # top edge
    samples.append(arr[h - bp:, :].flatten())    # bottom edge
    samples.append(arr[bp:h - bp, :bp].flatten())   # left edge (excl. corners)
    samples.append(arr[bp:h - bp, w - bp:].flatten())  # right edge (excl. corners)

    all_pixels = np.concatenate(samples)
    return float(np.median(all_pixels))


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """Preprocess the image for improved OCR on dark backgrounds.

    This is the main entry point for Node 2 (ImagePreprocessor).

    Samples border pixels to determine median brightness.  If the image
    has a dark background (median brightness < 128), an inverted copy
    is created to give Tesseract the dark-text-on-light-background input
    it needs for reliable extraction.

    Light-background images are returned unchanged.

    **Invariant**: The returned image is used ONLY by OCRExtractor and
    LanguageDetector.  The original unmodified image must always be
    passed to ImageCompositor and downstream nodes.

    Args:
        image: The original PIL Image from InputValidator.

    Returns:
        A PIL Image suitable for OCR — either the original (light
        background) or an inverted copy (dark background).
    """
    median_brightness = _sample_border_brightness(image)

    if median_brightness < 128:
        # Dark background — invert to produce dark-text-on-light for Tesseract
        return ImageOps.invert(image.convert("RGB"))

    # Light background — pass through unchanged
    return image
