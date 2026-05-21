from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file.

    All configuration values are centralised here — no hardcoded values
    anywhere else in the codebase.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    GEMINI_API_KEY: str
    MAX_FILE_SIZE_MB: int = 10
    MIN_OCR_CONFIDENCE: int = 40
    MIN_BBOX_AREA: int = 100
    GEMINI_MODEL: str = "gemini-1.5-flash"
    LANGDETECT_MIN_CONFIDENCE: float = 0.9


def get_settings() -> Settings:
    """Factory for the settings singleton.

    Called by route handlers via ``Depends(get_settings)`` so the object
    is injectable and testable.
    """
    return Settings()
