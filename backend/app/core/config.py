import os
from typing import List


class Settings:
    """Central configuration.

    V1 principle: keep V0 API backward compatible; only add flags.
    """

    PROJECT_NAME: str = "OCR Agent Service"
    API_V1_STR: str = "/api/v1"

    # -----------------------------
    # Service metadata
    # -----------------------------
    APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")
    BUILD_COMMIT: str = os.getenv("BUILD_COMMIT", "")
    BUILD_DATE: str = os.getenv("BUILD_DATE", "")

    # -----------------------------
    # CORS
    # -----------------------------
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # -----------------------------
    # Storage / runtime
    # -----------------------------
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    RUNTIME_DIR: str = os.getenv("RUNTIME_DIR", "runtime")
    LOG_JSONL_PATH: str = os.getenv("LOG_JSONL_PATH", os.path.join(RUNTIME_DIR, "logs.jsonl"))
    ARTIFACTS_DIR: str = os.getenv("ARTIFACTS_DIR", os.path.join(RUNTIME_DIR, "artifacts"))

    # -----------------------------
    # Retention / limits
    # -----------------------------
    ZERO_RETENTION_DEFAULT: bool = os.getenv("ZERO_RETENTION_DEFAULT", "true").lower() == "true"
    MAX_DOCS_PER_BATCH: int = int(os.getenv("MAX_DOCS_PER_BATCH", "20"))
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "20"))

    # -----------------------------
    # OCR engine
    # -----------------------------
    OCR_ENGINE_DEFAULT: str = os.getenv("OCR_ENGINE_DEFAULT", "tesseract")

    # -----------------------------
    # PDF rendering
    # -----------------------------
    PDF_RENDER_DPI: int = int(os.getenv("PDF_RENDER_DPI", "300"))

    # -----------------------------
    # Preprocessing (V1)
    # -----------------------------
    PREPROCESS_ENABLE: bool = os.getenv("PREPROCESS_ENABLE", "true").lower() == "true"
    PREPROCESS_DESKEW: bool = os.getenv("PREPROCESS_DESKEW", "true").lower() == "true"
    PREPROCESS_DENOISE: bool = os.getenv("PREPROCESS_DENOISE", "true").lower() == "true"
    PREPROCESS_THRESHOLD: bool = os.getenv("PREPROCESS_THRESHOLD", "true").lower() == "true"
    PREPROCESS_RESIZE_MIN_SIDE: int = int(os.getenv("PREPROCESS_RESIZE_MIN_SIDE", "1200"))

    # Debug artifacts: OFF in production by default
    SAVE_DEBUG_ARTIFACTS: bool = os.getenv("SAVE_DEBUG_ARTIFACTS", "false").lower() == "true"


settings = Settings()
