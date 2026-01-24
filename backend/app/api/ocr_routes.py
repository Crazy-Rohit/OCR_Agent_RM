from fastapi import APIRouter, UploadFile, File, Form, Query
from typing import List

from app.models.schemas import OCRBatchResponse, OCRBatchItem
from app.services.ocr_service import process_file
from app.services import file_service

router = APIRouter()


@router.post("/ocr")
async def ocr_single(
    file: UploadFile = File(...),
    document_type: str = Form("generic"),
    zero_retention: bool = Form(True),
    enable_layout: bool = Query(True),
):
    content = await file.read()
    return process_file(
        content,
        file.filename,
        document_type,
        zero_retention=zero_retention,
        enable_layout=enable_layout,
    )


@router.post("/ocr/batch", response_model=OCRBatchResponse)
async def ocr_batch(
    files: List[UploadFile] = File(...),
    document_type: str = Form("generic"),
    zero_retention: bool = Form(True),
    enable_layout: bool = Query(True),
):
    max_docs_allowed = getattr(file_service, "MAX_DOCS_ALLOWED", 10)

    results: List[OCRBatchItem] = []

    for f in files:
        content = await f.read()

        # If you already have a hash/duplicate mechanism in your codebase,
        # keep using it. Here is a safe fallback:
        file_hash = file_service.hash_bytes(content) if hasattr(file_service, "hash_bytes") else f.filename

        try:
            resp = process_file(
                content,
                f.filename,
                document_type,
                zero_retention=zero_retention,
                enable_layout=enable_layout,
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

    return OCRBatchResponse(
        status="success",
        document_type=document_type,
        zero_retention=bool(zero_retention),
        max_docs_allowed=max_docs_allowed,
        results=results,
    )
