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

    # Document safety limits (backend hardening)
    # NOTE: these are enforced BEFORE heavy OCR to avoid resource exhaustion.
    MAX_PAGES_PER_DOC: int = Field(default=50, ge=1)
    MAX_IMAGE_MEGAPIXELS: float = Field(default=20.0, ge=1.0)

    # Global OCR time budget (seconds). 0 disables.
    OCR_GLOBAL_TIMEOUT_S: int = Field(default=120, ge=0)

    # Optional engine orchestration settings
    ENABLE_DOCTR: bool = Field(default=False)
    ENABLE_TROCR: bool = Field(default=False)
    ENGINE_TIMEOUT_DOCTR_S: int = Field(default=25, ge=1)
    ENGINE_TIMEOUT_TROCR_S: int = Field(default=25, ge=1)
    ORCH_MAX_TROCR_REGIONS: int = Field(default=12, ge=1)
    ORCH_MAX_DOCTR_PAGES: int = Field(default=6, ge=0)
    DOCTR_ONLY_IF_TABLE_CANDIDATE: bool = Field(default=True)

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
