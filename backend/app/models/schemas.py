from __future__ import annotations

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class OCRWord(BaseModel):
    text: str
    confidence: Optional[float] = None
    bbox: Optional[List[int]] = None  # [x1,y1,x2,y2]


class OCRLine(BaseModel):
    text: str = ""
    bbox: Dict[str, int] = Field(default_factory=dict)
    words: List[Dict[str, Any]] = Field(default_factory=list)


class OCRBlock(BaseModel):
    text: str = ""
    bbox: Dict[str, int] = Field(default_factory=dict)
    lines: List[OCRLine] = Field(default_factory=list)


class PageText(BaseModel):
    page_number: int
    text: str = ""
    # Phase 1
    words: List[Dict[str, Any]] = Field(default_factory=list)
    # Phase 2
    lines: List[OCRLine] = Field(default_factory=list)
    blocks: List[OCRBlock] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    # Phase 3 early
    text_normalized: str = ""
    quality: Dict[str, Any] = Field(default_factory=dict)
    stats: Dict[str, Any] = Field(default_factory=dict)


class OCRResponse(BaseModel):
    job_id: str
    status: str
    document_type: str
    pages: List[PageText]
    full_text: str
    metadata: Dict[str, Any]


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
