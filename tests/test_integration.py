from __future__ import annotations

import base64
import json
import os
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import get_settings, Settings
from app.main import app


client = TestClient(app)

_SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_images_for_candidates"
_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "output"

TRANSLATION_MAP = {
    "oferta especial": "Special Offer",
    "aceite de oliva": "Olive Oil",
    "instrucciones": "Instructions",
    "envío gratis": "Free Shipping",
    "envio gratis": "Free Shipping",
    "ingredientes": "Ingredients",
    "gran venta": "Big Sale",
    "precaución": "Caution",
    "precaucion": "Caution",
    "auriculares": "Headphones",
    "descuento": "Discount",
    "extra virgen": "Extra Virgin",
    "ingredientes:": "Ingredients:",
    "agua, aceite": "Water, Oil",
    "atención": "Attention",
    "atencion": "Attention",
    "con micrófono": "With Microphone",
}


def _mock_gemini_translation(prompt: str) -> str:
    """Mock Gemini API response by mapping Spanish words in the prompt to English."""
    # Find the numbered list lines
    lines = prompt.strip().split("\n")
    items_to_translate: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Check if it starts with "1. ", "2. ", etc.
        parts = line.split(".", 1)
        if len(parts) == 2 and parts[0].strip().isdigit():
            items_to_translate.append(parts[1].strip())

    translations: list[str] = []
    for item in items_to_translate:
        item_lower = item.lower()
        matched = False
        for key, val in TRANSLATION_MAP.items():
            if key in item_lower:
                translations.append(val)
                matched = True
                break
        if not matched:
            translations.append(f"Translated {item}")

    return json.dumps(translations)


@pytest.fixture(autouse=True)
def override_settings() -> None:
    def get_test_settings() -> Settings:
        return Settings(
            GEMINI_API_KEY="test-key-not-real",
            MAX_FILE_SIZE_MB=10,
            MIN_OCR_CONFIDENCE=40,
            GEMINI_MODEL="gemini-1.5-flash",
        )
    app.dependency_overrides[get_settings] = get_test_settings
    yield
    app.dependency_overrides.pop(get_settings, None)


def test_integration_run_all_samples() -> None:
    """End-to-end integration test against all 8 sample images.

    Fails if any image cannot be processed, or if the output is not
    valid JSON, or if the output base64 cannot be parsed back as a valid
    JPEG image. Saves the output images in tests/output/ for visual
    verification.
    """
    assert _SAMPLE_DIR.exists(), f"Sample images directory not found at {_SAMPLE_DIR}"
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    sample_files = list(_SAMPLE_DIR.glob("*.png"))
    assert len(sample_files) > 0, "No sample images found to test"

    # Mock the Gemini API generation call
    mock_response = MagicMock()
    # We patch generate_content so we can dynamically translate based on prompt content
    with patch("app.pipeline.translator.genai.GenerativeModel") as mock_model_class:
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model

        def side_effect(prompt: str) -> MagicMock:
            res = MagicMock()
            res.text = _mock_gemini_translation(prompt)
            return res

        mock_model.generate_content.side_effect = side_effect

        for file_path in sample_files:
            print(f"Testing integration on: {file_path.name}")
            with open(file_path, "rb") as f:
                img_bytes = f.read()

            response = client.post(
                "/api/v1/translate-image",
                files={"file": (file_path.name, img_bytes, "image/png")},
            )

            # Assert API succeeded
            assert response.status_code == 200, f"Failed on {file_path.name}: {response.text}"
            data = response.json()

            # Assert output structure
            assert "status" in data
            assert "output_image" in data
            assert data["output_format"] == "jpeg"

            # Parse image back to verify it is valid JPEG
            img_data = base64.b64decode(data["output_image"])
            assert img_data[:2] == b"\xff\xd8", "Not a valid JPEG start signature"

            out_img = Image.open(BytesIO(img_data))
            assert out_img.size[0] > 0
            assert out_img.size[1] > 0

            # Save the image to the output directory for visual inspection
            out_filename = file_path.stem + "_translated.jpg"
            out_path = _OUTPUT_DIR / out_filename
            out_img.save(out_path, format="JPEG")
            print(f"Saved visual verification output to {out_path}")
