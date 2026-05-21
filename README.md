# Image Text Translation Pipeline

A stateless REST API that accepts a product image containing text in a foreign
language and returns a version of that image with all detected text replaced by
its English translation. Built as a prototype for a B2B e-commerce platform.

## Setup

### Prerequisites

- Python 3.11+
- Tesseract OCR 5.x installed and on PATH
- A Gemini API key

### Installation

```bash
# Create virtual environment
py -3.11 -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and fill in your Gemini API key:

```bash
cp .env.example .env
```

### Running

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

### Health Check

```bash
curl http://localhost:8000/api/v1/health
```

## Known Limitations

- **Prototype boundary**: Built as a proof-of-concept prototype, not for production deployment.
- **No authentication or rate limiting**: The endpoints are open and unsecured.
- **Single image per request**: Batch processing of multiple images in a single API call is out of scope.
- **Text alignment is not reconstructed**: Centered or right-aligned text is rendered left-aligned. All translated text is drawn left-aligned from the original bounding box origin.
- **Font weight and style are not preserved**: Bold, italic, and heavy weight variations are rendered using the single regular-weight font (NotoSans-Regular).
- **Non-text symbols rendered inconsistently**: Non-text and decorative Unicode characters (such as list bullets `•`) may be stripped out by the OCR noise filter.
- **Mixed-background images partially fail**: Full-dark or full-light backgrounds are detected globally, but images containing both dark and light sections (e.g. dark headers with light cream bodies) are not preprocessed per-region.
- **Complex layout constraints**: Rotated, vertical, or overlapping text layouts are not supported.
- **No Latin-script early-return**: The English early-return optimization is not implemented for Latin-script languages. All images with detectable text are sent to Gemini for translation. Gemini handles the case where text is already in English by returning it unchanged.

