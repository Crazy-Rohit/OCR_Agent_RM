from typing import List, Dict, Any
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
