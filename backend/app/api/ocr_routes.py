import hashlib
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.core.config import settings
from app.models.schemas import OCRResponse, OCRBatchResponse, OCRBatchItem
from app.services.ocr_service import process_file


router = APIRouter(prefix="/ocr", tags=["OCR"])


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_bool(val: Optional[str], default: bool) -> bool:
    if val is None:
        return default
    v = str(val).strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


@router.post("/extract", response_model=OCRResponse)
async def extract_text(
    file: UploadFile = File(...),
    document_type: str = Form("generic"),
    zero_retention: Optional[str] = Form(None),
):
    try:
        zr = parse_bool(zero_retention, settings.ZERO_RETENTION_DEFAULT)

        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Empty file")

        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if len(contents) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File exceeds max size of {settings.MAX_FILE_SIZE_MB} MB",
            )

        return process_file(contents, file.filename or "document", document_type, zero_retention=zr)

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-batch", response_model=OCRBatchResponse)
async def extract_batch(
    files: List[UploadFile] = File(...),
    document_type: str = Form("generic"),
    zero_retention: Optional[str] = Form(None),
):
    """
    Batch OCR:
    - supports many files per request
    - skips duplicates:
        (a) same filename in the batch
        (b) same content hash in the batch
    """
    zr = parse_bool(zero_retention, settings.ZERO_RETENTION_DEFAULT)

    if len(files) > settings.MAX_DOCS_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Received {len(files)} but max allowed is {settings.MAX_DOCS_PER_BATCH}.",
        )

    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

    seen_names = set()
    seen_hashes = set()
    results: List[OCRBatchItem] = []

    for f in files:
        filename = f.filename or "document"

        try:
            contents = await f.read()
            if not contents:
                results.append(OCRBatchItem(filename=filename, file_hash="", error="Empty file"))
                continue

            if len(contents) > max_bytes:
                results.append(
                    OCRBatchItem(
                        filename=filename,
                        file_hash="",
                        error=f"File exceeds max size of {settings.MAX_FILE_SIZE_MB} MB",
                    )
                )
                continue

            # --- duplicate by name ---
            if filename in seen_names:
                results.append(
                    OCRBatchItem(
                        filename=filename,
                        file_hash="",
                        skipped_duplicate=True,
                        reason="duplicate_filename_in_batch",
                    )
                )
                continue
            seen_names.add(filename)

            # --- duplicate by content hash ---
            h = sha256_bytes(contents)
            if h in seen_hashes:
                results.append(
                    OCRBatchItem(
                        filename=filename,
                        file_hash=h,
                        skipped_duplicate=True,
                        reason="duplicate_content_in_batch",
                    )
                )
                continue
            seen_hashes.add(h)

            resp = process_file(contents, filename, document_type, zero_retention=zr)

            results.append(
                OCRBatchItem(
                    filename=filename,
                    file_hash=h,
                    skipped_duplicate=False,
                    response=resp,
                )
            )

        except ValueError as ve:
            results.append(OCRBatchItem(filename=filename, file_hash="", error=str(ve)))
        except Exception as e:
            results.append(OCRBatchItem(filename=filename, file_hash="", error=str(e)))

    return OCRBatchResponse(
        status="success",
        document_type=document_type,
        zero_retention=zr,
        max_docs_allowed=settings.MAX_DOCS_PER_BATCH,
        results=results,
    )
