from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NormWord(BaseModel):
    text: str
    bbox: Optional[List[int]] = None  # [x1,y1,x2,y2]
    confidence: Optional[float] = None


class NormLine(BaseModel):
    text: str
    words: List[NormWord] = Field(default_factory=list)


class NormBlock(BaseModel):
    # heading | paragraph | list_item | table_region | unknown
    type: str = "paragraph"
    text: str = ""
    text_normalized: str = ""
    lines: List[NormLine] = Field(default_factory=list)
    bbox: Dict[str, int] = Field(default_factory=dict)

    # Optional structure hints for downstream (no breaking)
    level: int = 0                 # heading/list nesting level (heuristic)
    marker: Optional[str] = None   # bullet/number marker if list_item
    table_candidate: bool = False  # heuristic table region flag


class NormPage(BaseModel):
    page_number: int
    blocks: List[NormBlock] = Field(default_factory=list)
    # printed | handwritten | mixed | unknown
    classification: str = "unknown"
    # optional diagnostic stats
    routing: Dict[str, Any] = Field(default_factory=dict)


class DocumentModel(BaseModel):
    pages: List[NormPage] = Field(default_factory=list)
    full_text: str = ""
    full_text_normalized: str = ""
    markdown: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
