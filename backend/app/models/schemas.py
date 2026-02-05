from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class PageText(BaseModel):
    page_number: int
    text: str


class OCRResponse(BaseModel):
    job_id: str
    status: str
    document_type: str
    pages: List[PageText]
    full_text: str
    metadata: Dict[str, Any]


# -----------------------------
# Batch response models
# -----------------------------

class OCRBatchItem(BaseModel):
    filename: str
    file_hash: str
    skipped_duplicate: bool = False
    reason: Optional[str] = None
    response: Optional[OCRResponse] = None
    error: Optional[str] = None


class OCRBatchResponse(BaseModel):
    status: str
    document_type: str
    zero_retention: bool
    max_docs_allowed: int
    results: List[OCRBatchItem]
