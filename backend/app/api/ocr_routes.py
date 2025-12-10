from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.models.schemas import OCRResponse
from app.services.ocr_service import process_file


router = APIRouter(prefix="/ocr", tags=["OCR"])


@router.post("/extract", response_model=OCRResponse)
async def extract_text(
    file: UploadFile = File(...),
    document_type: str = Form("generic"),
):
    """
    Main OCR endpoint:
    - Accepts PDF / image / DOCX
    - Returns standard OCRResponse with pages + full_text
    """
    try:
        contents = await file.read()
        result = process_file(contents, file.filename, document_type)
        return result
    except ValueError as ve:
        # e.g. unsupported file type
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
