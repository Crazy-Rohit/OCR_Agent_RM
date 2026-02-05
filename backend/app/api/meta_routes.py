from __future__ import annotations

import platform
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import settings


router = APIRouter(tags=["meta"])


@router.get("/version")
def version() -> dict:
    now_utc = datetime.now(timezone.utc).isoformat()
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.APP_VERSION,
        "build": {"commit": settings.BUILD_COMMIT, "date": settings.BUILD_DATE},
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "timestamp_utc": now_utc,
        },
    }


@router.get("/capabilities")
def capabilities() -> dict:
    return {
        "supported_input_types": ["pdf", "image", "docx"],
        "supported_image_extensions": ["jpg", "jpeg", "png", "bmp", "tif", "tiff"],
        "supported_document_extensions": ["pdf", "docx"],
        "features": {
            "batch": True,
            "layout": True,
            "tables": True,
            "preprocess": True,
            "classification": True,
            "zero_retention": True,
        },
        "defaults": {
            "api_prefix": settings.API_V1_STR,
            "zero_retention_default": bool(settings.ZERO_RETENTION_DEFAULT),
            "max_docs_per_batch": int(settings.MAX_DOCS_PER_BATCH),
            "max_file_size_mb": int(settings.MAX_FILE_SIZE_MB),
            "pdf_render_dpi": int(settings.PDF_RENDER_DPI),
            "preprocess_enable": bool(settings.PREPROCESS_ENABLE),
        },
        "engine": {
            "name": settings.OCR_ENGINE_DEFAULT,
            "tesseract_cmd_env": "TESSERACT_CMD",
        },
    }
