# backend/app/core/config.py
from __future__ import annotations

from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Load from environment + optional .env
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    PROJECT_NAME: str = Field(default="OCR Agent")
    API_V1_STR: str = Field(default="/api/v1")

    # CORS (your frontend is typically on Vite:5173)
    # You can override in .env as JSON:
    # BACKEND_CORS_ORIGINS='["http://localhost:5173","http://127.0.0.1:5173"]'
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # Upload/storage
    UPLOAD_DIR: str = Field(default="uploads")
    MAX_FILE_SIZE_MB: int = Field(default=20, ge=1)

    # Batch limits
    MAX_DOCS_PER_BATCH: int = Field(default=10, ge=1)

    # PDF rendering (if you convert PDFs to images before OCR)
    PDF_RENDER_DPI: int = Field(default=200, ge=72, le=600)

    # Retention behavior
    ZERO_RETENTION_DEFAULT: bool = Field(default=True)

    # OCR Phase 2 defaults (confidence filtering)
    OCR_MIN_WORD_CONF: int = Field(default=60, ge=0, le=100)
    OCR_MIN_WORD_LEN: int = Field(default=1, ge=0)


settings = Settings()
