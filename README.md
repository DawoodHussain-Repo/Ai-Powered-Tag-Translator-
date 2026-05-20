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

- Prototype only — not for production deployment
- No authentication or rate limiting
- Single image per request (no batch processing)
- Output uses NotoSans font, not the original typeface
- Complex overlapping or rotated text is not handled
