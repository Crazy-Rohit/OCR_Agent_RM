from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class WordBox(BaseModel):
    text: str
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: Optional[float] = None


class LineBox(BaseModel):
    text: str
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: Optional[float] = None


class BlockBox(BaseModel):
    block_type: str = "text"  # "text" | "header" | "footer" | "table"
    text: str
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: Optional[float] = None
    line_indexes: Optional[List[int]] = None


class TableBox(BaseModel):
    text: str
    x1: int
    y1: int
    x2: int
    y2: int
    line_indexes: Optional[List[int]] = None

    # ✅ structured table (optional)
    rows: Optional[List[List[str]]] = None
    n_rows: Optional[int] = None
    n_cols: Optional[int] = None


class PageText(BaseModel):
    page_number: int
    text: str
    words: Optional[List[WordBox]] = None
    lines: Optional[List[LineBox]] = None
    blocks: Optional[List[BlockBox]] = None
    tables: Optional[List[TableBox]] = None


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
