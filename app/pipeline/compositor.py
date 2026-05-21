from __future__ import annotations

import os
import statistics
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.exceptions import CompositorError
from app.models.schemas import TranslatedBlock

# Resolve the font path relative to the project root.
# The font is checked into the repository at assets/fonts/NotoSans-Regular.ttf.
_FONT_PATH = str(
    Path(__file__).resolve().parent.parent.parent / "assets" / "fonts" / "NotoSans-Regular.ttf"
)

_MIN_FONT_SIZE: int = 8


def _clamp_bbox(
    bbox: tuple[int, int, int, int],
    img_width: int,
    img_height: int,
) -> tuple[int, int, int, int]:
    """Clamp bounding box coordinates to image dimensions.

    Invariant 6: coordinates are always validated before any PIL draw call
    to prevent out-of-bounds errors on edge-case OCR results.

    Args:
        bbox: (x, y, w, h) from the OCR/translation pipeline.
        img_width: Width of the image in pixels.
        img_height: Height of the image in pixels.

    Returns:
        Clamped (x, y, w, h) within valid image bounds.
    """
    x, y, w, h = bbox
    x = max(0, min(x, img_width - 1))
    y = max(0, min(y, img_height - 1))
    w = max(1, min(w, img_width - x))
    h = max(1, min(h, img_height - y))
    return (x, y, w, h)


def _sample_background_color(
    image: Image.Image,
    x: int,
    y: int,
    w: int,
    h: int,
    border: int = 5,
) -> tuple[int, ...]:
    """Sample the background color from a border around the bounding box.

    Takes pixels from a 5-pixel border around the bbox and returns the
    median pixel value per channel.  Does not assume white or any fixed
    background color.
    """
    pixels: list[tuple[int, ...]] = []
    img_w, img_h = image.size

    # Top border
    for bx in range(max(0, x - border), min(img_w, x + w + border)):
        for by in range(max(0, y - border), min(img_h, y)):
            pixels.append(image.getpixel((bx, by)))

    # Bottom border
    for bx in range(max(0, x - border), min(img_w, x + w + border)):
        for by in range(max(0, y + h), min(img_h, y + h + border)):
            pixels.append(image.getpixel((bx, by)))

    # Left border
    for by in range(max(0, y), min(img_h, y + h)):
        for bx in range(max(0, x - border), min(img_w, x)):
            pixels.append(image.getpixel((bx, by)))

    # Right border
    for by in range(max(0, y), min(img_h, y + h)):
        for bx in range(max(0, x + w), min(img_w, x + w + border)):
            pixels.append(image.getpixel((bx, by)))

    if not pixels:
        # Fallback: if no border pixels available, use white
        n_channels = len(image.getbands())
        return tuple([255] * n_channels)

    # Median per channel
    n_channels = len(pixels[0])
    return tuple(
        int(statistics.median(p[ch] for p in pixels))
        for ch in range(n_channels)
    )


def _sample_foreground_color(
    image: Image.Image,
    x: int,
    y: int,
    w: int,
    h: int,
    bg_color: tuple[int, ...] | None = None,
) -> tuple[int, ...]:
    """Sample the text (foreground) color from within the bounding box.

    If the background is dark (luminance < 128), uses the median of the
    lightest pixels within the bbox. If the background is light, uses
    the median of the darkest pixels.
    """
    pixels: list[tuple[int, ...]] = []
    img_w, img_h = image.size

    for bx in range(max(0, x), min(img_w, x + w)):
        for by in range(max(0, y), min(img_h, y + h)):
            pixels.append(image.getpixel((bx, by)))

    if not pixels:
        n_channels = len(image.getbands())
        return tuple([0] * n_channels)

    if bg_color is None:
        bg_color = _sample_background_color(image, x, y, w, h)

    if len(bg_color) >= 3:
        bg_luminance = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
    else:
        bg_luminance = bg_color[0]

    if bg_luminance < 128:
        # Dark background -> text is light. Sort descending by luminance.
        pixels.sort(
            key=lambda p: 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] if len(p) >= 3 else p[0],
            reverse=True,
        )
    else:
        # Light background -> text is dark. Sort ascending by luminance.
        pixels.sort(
            key=lambda p: 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] if len(p) >= 3 else p[0],
            reverse=False,
        )

    top_quarter = pixels[: max(1, len(pixels) // 4)]

    n_channels = len(top_quarter[0])
    return tuple(
        int(statistics.median(p[ch] for p in top_quarter))
        for ch in range(n_channels)
    )


def _auto_scale_font(
    text: str,
    bbox_width: int,
    bbox_height: int,
    font_path: str,
) -> tuple[ImageFont.FreeTypeFont, str]:
    """Auto-scale font size to fit text within the bounding box.

    Starts from the bbox height as the initial font size and reduces in
    steps of 1pt until the rendered text width fits within bbox width
    minus 2px padding.

    Minimum font size is 8pt.  If text still cannot fit at 8pt, it is
    truncated with an ellipsis.

    Returns:
        A tuple of (font, display_text) where display_text may be
        truncated with ellipsis if it could not fit.
    """
    padding = 2
    target_width = max(1, bbox_width - padding)
    display_text = text

    # Start from bbox height
    font_size = max(_MIN_FONT_SIZE, bbox_height)

    while font_size >= _MIN_FONT_SIZE:
        try:
            font = ImageFont.truetype(font_path, font_size)
        except OSError:
            font = ImageFont.load_default()
            return font, display_text

        text_bbox = font.getbbox(display_text)
        text_width = text_bbox[2] - text_bbox[0]

        if text_width <= target_width:
            return font, display_text

        font_size -= 1

    # At minimum font size — truncate with ellipsis if still too wide
    font = ImageFont.truetype(font_path, _MIN_FONT_SIZE)
    while len(display_text) > 1:
        candidate = display_text[:-1] + "…"
        text_bbox = font.getbbox(candidate)
        text_width = text_bbox[2] - text_bbox[0]
        if text_width <= target_width:
            return font, candidate
        display_text = display_text[:-1]

    return font, display_text


def composite_image(
    original: Image.Image,
    translated_blocks: list[TranslatedBlock],
) -> Image.Image:
    """Erase original text regions and draw translated text.

    This is the main entry point for Node 5.

    Invariant 1: The original image is never mutated — all compositing
    operates on a ``.copy()`` of the PIL Image object.

    Invariant 6: All bounding box coordinates are clamped to image
    dimensions before any draw call.

    Args:
        original: The original PIL Image (never mutated).
        translated_blocks: Blocks with translated text and bounding boxes.

    Returns:
        A new PIL Image with translated text composited.

    Raises:
        CompositorError: If compositing fails.
    """
    if not translated_blocks:
        return original.copy()

    try:
        # Invariant 1: work on a copy
        output = original.copy()

        # Ensure RGB mode for consistent colour sampling
        if output.mode != "RGB":
            output = output.convert("RGB")

        original_rgb = original
        if original_rgb.mode != "RGB":
            original_rgb = original_rgb.convert("RGB")

        draw = ImageDraw.Draw(output)

        for block in translated_blocks:
            x, y, w, h = _clamp_bbox(
                block.bbox, output.width, output.height
            )

            # --- Step A: Sample colours BEFORE erasure ---
            bg_color = _sample_background_color(original_rgb, x, y, w, h)
            fg_color = _sample_foreground_color(original_rgb, x, y, w, h, bg_color)

            # --- Step A: Erase original text ---
            draw.rectangle(
                [(x, y), (x + w - 1, y + h - 1)],
                fill=bg_color,
            )

            # Apply slight gaussian blur to the filled region to reduce
            # hard edges
            region = output.crop((x, y, x + w, y + h))
            region = region.filter(ImageFilter.GaussianBlur(radius=1))
            output.paste(region, (x, y))

            # Re-create draw after paste
            draw = ImageDraw.Draw(output)

            # --- Step B: Render translated text ---
            font, display_text = _auto_scale_font(
                block.translated_text, w, h, _FONT_PATH
            )

            draw.text(
                (x, y),
                display_text,
                fill=fg_color,
                font=font,
            )

        return output

    except Exception as exc:
        if isinstance(exc, CompositorError):
            raise
        raise CompositorError(
            f"Image compositing failed: {exc}"
        ) from exc
