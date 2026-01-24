import os
from typing import List


class Settings:
    PROJECT_NAME: str = "OCR Agent Service"
    API_V1_STR: str = "/api/v1"

    # CORS – allow all origins in dev. Tighten in prod.
    BACKEND_CORS_ORIGINS: List[str] = ["*"]

    # Where uploaded files (optional) will be stored
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")

    # -----------------------------
    # Phase 1 controls
    # -----------------------------
    # Privacy-first: do not store files by default
    ZERO_RETENTION_DEFAULT: bool = os.getenv("ZERO_RETENTION_DEFAULT", "true").lower() == "true"

    # Batch limit (increase this safely)
    MAX_DOCS_PER_BATCH: int = int(os.getenv("MAX_DOCS_PER_BATCH", "20"))

    # Max size per file in MB (protects RAM)
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "20"))


settings = Settings()
