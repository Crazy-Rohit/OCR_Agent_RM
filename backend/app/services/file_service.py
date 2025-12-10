import os
from app.core.config import settings


BASE_UPLOAD_DIR = settings.UPLOAD_DIR
os.makedirs(BASE_UPLOAD_DIR, exist_ok=True)


def save_file(job_id: str, filename: str, file_bytes: bytes) -> str:
    job_dir = os.path.join(BASE_UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    path = os.path.join(job_dir, filename)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path
