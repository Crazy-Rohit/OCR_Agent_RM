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
    level: int = 0
    marker: Optional[str] = None
    checkbox: Optional[Dict[str, Any]] = None
    table_candidate: bool = False

    # Engine provenance (optional)
    engine: Optional[str] = None
    text_engine: Optional[str] = None
    form_box_region: bool = False

    # Handwriting routing (non-destructive)
    # printed | handwritten | unknown
    script: Optional[str] = None
    handwriting_score: Optional[float] = None
    handwriting_signals: Dict[str, Any] = Field(default_factory=dict)



class FormField(BaseModel):
    key: str
    value: str
    method: str = "unknown"  # box_ocr | trocr | tesseract | manual
    bbox: Optional[List[int]] = None
    confidence: Optional[float] = None


class NormPage(BaseModel):
    page_number: int
    blocks: List[NormBlock] = Field(default_factory=list)
    classification: str = "unknown"  # printed | handwritten | mixed | unknown
    routing: Dict[str, Any] = Field(default_factory=dict)


    # Engine provenance per-page (populated by engine_orchestrator)
    engine_usage: Dict[str, Any] = Field(default_factory=dict)

    # Per-page diagnostics (errors, skip reasons, debug metrics)
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class NormTableCell(BaseModel):
    row: int
    col: int
    text: str = ""
    bbox: Optional[List[int]] = None  # [x1,y1,x2,y2]
    confidence: Optional[float] = None


class NormTable(BaseModel):
    page_number: int
    source_block_index: Optional[int] = None
    bbox: Optional[List[int]] = None  # [x1,y1,x2,y2]
    n_rows: int = 0
    n_cols: int = 0
    cells: List[NormTableCell] = Field(default_factory=list)
    method: str = "bbox_grid_heuristic"
    score: Optional[float] = None


class NormChunk(BaseModel):
    chunk_id: str
    page_number: int
    block_indices: List[int] = Field(default_factory=list)
    text: str


class DocumentModel(BaseModel):
    pages: List[NormPage] = Field(default_factory=list)
    tables: List[NormTable] = Field(default_factory=list)
    chunks: List[NormChunk] = Field(default_factory=list)

    full_text: str = ""
    full_text_normalized: str = ""
    markdown: str = ""
    html: str = ""

    diagnostics: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
