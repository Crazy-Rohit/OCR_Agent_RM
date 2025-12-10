import os
from typing import List


class Settings:
    PROJECT_NAME: str = "OCR Agent Service"
    API_V1_STR: str = "/api/v1"

    # CORS – allow all origins in dev. Tighten in prod.
    BACKEND_CORS_ORIGINS: List[str] = [
        "*",
    ]

    # Where uploaded files (optional) will be stored
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")


settings = Settings()
