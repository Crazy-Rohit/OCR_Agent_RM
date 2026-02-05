from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from app.core.config import settings
from app.core.telemetry import write_jsonl
from app.models.schemas import OCRBatchItem, OCRBatchResponse
from app.services import file_service
from app.services.ocr_service import process_file


router = APIRouter()


def _enforce_max_file_size(filename: str, content: bytes) -> None:
    max_bytes = int(settings.MAX_FILE_SIZE_MB) * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "file_too_large",
                "filename": filename,
                "max_file_size_mb": int(settings.MAX_FILE_SIZE_MB),
            },
        )


@router.post("/ocr")
async def ocr_single(
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("generic"),
    zero_retention: bool = Form(True),
    enable_layout: bool = Query(True),
    preprocess: Optional[bool] = Query(None),
):
    """Single-document OCR.

    Backward compatible with V0: new param `preprocess` is optional.
    """
    request_id = getattr(request.state, "request_id", None)
    content = await file.read()
    _enforce_max_file_size(file.filename, content)

    write_jsonl(
        {
            "event": "ocr_single_start",
            "request_id": request_id,
            "filename": file.filename,
            "document_type": document_type,
            "zero_retention": bool(zero_retention),
            "enable_layout": bool(enable_layout),
            "preprocess": preprocess,
            "bytes": len(content),
        }
    )

    resp = process_file(
        content,
        file.filename,
        document_type,
        zero_retention=zero_retention,
        enable_layout=enable_layout,
        preprocess=preprocess,
        request_id=request_id,
    )

    write_jsonl(
        {
            "event": "ocr_single_end",
            "request_id": request_id,
            "filename": file.filename,
        }
    )
    return resp


@router.post("/ocr/batch", response_model=OCRBatchResponse)
async def ocr_batch(
    request: Request,
    files: List[UploadFile] = File(...),
    document_type: str = Form("generic"),
    zero_retention: bool = Form(True),
    enable_layout: bool = Query(True),
    preprocess: Optional[bool] = Query(None),
):
    """Batch OCR (backward compatible)."""
    request_id = getattr(request.state, "request_id", None)

    max_docs_allowed = int(getattr(settings, "MAX_DOCS_PER_BATCH", 20))
    if len(files) > max_docs_allowed:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "too_many_files",
                "max_docs_allowed": max_docs_allowed,
                "received": len(files),
            },
        )

    write_jsonl(
        {
            "event": "ocr_batch_start",
            "request_id": request_id,
            "count": len(files),
            "document_type": document_type,
            "zero_retention": bool(zero_retention),
            "enable_layout": bool(enable_layout),
            "preprocess": preprocess,
        }
    )

    results: List[OCRBatchItem] = []

    for f in files:
        content = await f.read()
        _enforce_max_file_size(f.filename, content)
        file_hash = file_service.hash_bytes(content)

        try:
            resp = process_file(
                content,
                f.filename,
                document_type,
                zero_retention=zero_retention,
                enable_layout=enable_layout,
                preprocess=preprocess,
                request_id=request_id,
            )
            results.append(
                OCRBatchItem(
                    filename=f.filename,
                    file_hash=str(file_hash),
                    skipped_duplicate=False,
                    response=resp,
                    error=None,
                )
            )
        except Exception as e:
            results.append(
                OCRBatchItem(
                    filename=f.filename,
                    file_hash=str(file_hash),
                    skipped_duplicate=False,
                    response=None,
                    error=str(e),
                )
            )

    write_jsonl(
        {
            "event": "ocr_batch_end",
            "request_id": request_id,
            "count": len(files),
        }
    )

    return OCRBatchResponse(
        status="success",
        document_type=document_type,
        zero_retention=bool(zero_retention),
        max_docs_allowed=max_docs_allowed,
        results=results,
    )
