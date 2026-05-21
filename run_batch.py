from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

# Use httpx which is already installed in our requirements.txt
try:
    import httpx
except ImportError:
    print("Error: 'httpx' is not installed in the current environment.")
    print("Please activate your virtual environment and run: pip install httpx")
    sys.exit(1)

# API endpoint details
API_URL = "http://127.0.0.1:8000/api/v1/translate-image"

# Default limit on number of images to process (set to None for no limit/all images)
DEFAULT_BATCH_LIMIT = None

# Default delay between processing images in seconds (to prevent rate limits/429)
DEFAULT_DELAY_SECONDS = 12.0


def process_image(file_path: Path, output_dir: Path) -> None:
    """Send a single image to the local translation API and save the result."""
    print(f"Processing: {file_path.name} ... ", end="", flush=True)

    # Determine MIME type based on extension
    ext = file_path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    elif ext == ".png":
        mime = "image/png"
    elif ext == ".webp":
        mime = "image/webp"
    else:
        print(f"Skipped (unsupported file extension '{ext}')")
        return

    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        # Send request as multipart/form-data
        files = {"file": (file_path.name, file_bytes, mime)}
        response = httpx.post(API_URL, files=files, timeout=60.0)

        if response.status_code == 200:
            data = response.json()
            status = data.get("status")
            blocks_translated = data.get("blocks_translated", 0)
            source_language = data.get("source_language")

            # Decode base64 image
            img_data = base64.b64decode(data["output_image"])

            # Save to output folder (as .jpg since the API returns JPEG format)
            out_name = f"{file_path.stem}_translated.jpg"
            out_path = output_dir / out_name
            with open(out_path, "wb") as out_f:
                out_f.write(img_data)

            print(
                f"Success! [Status: {status}] [Lang: {source_language}] [Blocks: {blocks_translated}] -> Saved to {out_path.name}"
            )
        else:
            # Succeeded connection but API returned error
            try:
                err_data = response.json()
                err_msg = f"{err_data.get('code')}: {err_data.get('error')}"
            except Exception:
                err_msg = response.text
            print(f"FAILED (HTTP {response.status_code}: {err_msg})")

    except httpx.ConnectError:
        print("\nError: Could not connect to the local API server.")
        print(f"Make sure you started the server with: uvicorn app.main:app --reload")
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}")


def main() -> None:
    # 1. Parse arguments or use default folders
    input_folder = Path("sample_images_for_candidates")
    output_folder = Path("translated_output")

    if len(sys.argv) > 1:
        input_folder = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_folder = Path(sys.argv[2])

    if not input_folder.exists() or not input_folder.is_dir():
        print(f"Error: Input folder '{input_folder}' does not exist or is not a directory.")
        print("Usage: python run_batch.py [input_folder] [output_folder]")
        sys.exit(1)

    output_folder.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f" B2B AI Text Replacer - Batch Process Tool")
    print("=" * 60)
    print(f"Input Directory:  {input_folder.absolute()}")
    print(f"Output Directory: {output_folder.absolute()}")
    print(f"Sending requests to: {API_URL}")
    print("=" * 60)

    # 2. Get all images in input folder
    supported_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    image_files = sorted(
        [p for p in input_folder.iterdir() if p.is_file() and p.suffix.lower() in supported_extensions]
    )

    if not image_files:
        print("No supported image files found (.jpg, .jpeg, .png, .webp).")
        return

    # 3. Process each image
    limit = DEFAULT_BATCH_LIMIT
    if len(sys.argv) > 3:
        try:
            val = sys.argv[3].lower()
            if val in ("none", "all"):
                limit = None
            else:
                limit = int(sys.argv[3])
        except ValueError:
            pass

    limit_str = str(limit) if limit is not None else "all"
    print(f"Processing up to {limit_str} images...")
    print("=" * 60)

    targets = image_files[:limit] if limit is not None else image_files
    for i, file_path in enumerate(targets):
        if i > 0 and DEFAULT_DELAY_SECONDS > 0:
            print(f"Waiting {DEFAULT_DELAY_SECONDS} seconds to respect API rate limits...")
            time.sleep(DEFAULT_DELAY_SECONDS)
        process_image(file_path, output_folder)

    print("=" * 60)
    print("Batch processing complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
