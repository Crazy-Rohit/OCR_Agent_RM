import os
import re
from pathlib import Path

from app.core.config import settings


BASE_UPLOAD_DIR = Path(settings.UPLOAD_DIR)
BASE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename(filename: str) -> str:
    """
    Keep filenames safe:
    - strip folders
    - remove dangerous chars
    """
    name = Path(filename).name
    name = re.sub(r"[^a-zA-Z0-9._ -]+", "_", name).strip()
    return name or "document"


def save_unique_by_name(filename: str, file_bytes: bytes) -> str:
    """
    Saves file to uploads/<filename>.
    If a file with the same name already exists, overwrite it
    so only ONE copy exists at all times.
    """
    safe = sanitize_filename(filename)
    path = BASE_UPLOAD_DIR / safe
    path.write_bytes(file_bytes)
    return str(path)


def delete_if_exists(filename: str) -> None:
    safe = sanitize_filename(filename)
    path = BASE_UPLOAD_DIR / safe
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
