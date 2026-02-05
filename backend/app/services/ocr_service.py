from __future__ import annotations

import io
import time
import uuid
from typing import List, Optional

from docx import Document

from app.classify.document_classifier import classify_from_signals
from app.core.config import settings
from app.engines.tesseract_engine import TesseractEngine
from app.models.schemas import OCRResponse, PageText
from app.pipeline.ingest import image_to_page, pdf_to_pages
from app.pipeline.preprocess import preprocess_image
from app.postprocess.layout_normalizer import normalize_pages
from app.services import file_service, layout_service


_ENGINE = TesseractEngine()


def _profile_for_category(category: str) -> str:
    if category == "screenshot":
        return "printed"
    if category == "scanned_pdf":
        return "scanned"
    if category == "handwritten_form":
        return "handwriting_hint"
    return "printed"


def _extract_from_docx(file_bytes: bytes) -> List[PageText]:
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs)
    return [PageText(page_number=1, text=text, words=None, lines=None, blocks=None, tables=None)]


def process_file(
    file_bytes: bytes,
    filename: str,
    document_type: str,
    *,
    zero_retention: bool | None = None,
    enable_layout: bool = True,
    preprocess: Optional[bool] = None,
    request_id: Optional[str] = None,
) -> OCRResponse:
    """Main OCR entrypoint used by the API.

    V1:
    - standardized ingest + preprocessing
    - classification in metadata
    - deterministic layout ordering
    - backward compatible schema
    """
    start = time.time()
    job_id = str(uuid.uuid4())

    if zero_retention is None:
        zero_retention = settings.ZERO_RETENTION_DEFAULT

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    pages: List[PageText] = []
    classifications = []

    if ext == "pdf":
        ingested = pdf_to_pages(file_bytes)
        for p in ingested:
            if p.text_layer:
                pages.append(
                    PageText(
                        page_number=p.page_number,
                        text=p.text_layer,
                        words=None,
                        lines=None,
                        blocks=None,
                        tables=None,
                    )
                )
                continue

            prep = preprocess_image(p.image, request_id=request_id, page_number=p.page_number, enable=preprocess)
            cls = classify_from_signals(
                blur_var=prep.blur_var,
                contrast=prep.contrast,
                edge_density=prep.edge_density,
            )
            classifications.append(cls)
            profile = _profile_for_category(cls.category)

            if enable_layout:
                res = _ENGINE.ocr(prep.image, with_words=True, profile=profile)
                words = res.words or []
                lines = layout_service.words_to_lines(words) if words else None
                blocks = layout_service.lines_to_blocks(lines) if lines else None
                tables = layout_service.detect_tables_from_lines(lines) if lines else None

                if tables and words and hasattr(layout_service, "structure_table_from_words"):
                    structured = []
                    for t in tables:
                        try:
                            structured.append(layout_service.structure_table_from_words(words, t))
                        except Exception:
                            structured.append(t)
                    tables = structured

                pages.append(
                    PageText(
                        page_number=p.page_number,
                        text=res.text,
                        words=words,
                        lines=lines,
                        blocks=blocks,
                        tables=tables,
                    )
                )
            else:
                res = _ENGINE.ocr(prep.image, with_words=False, profile=profile)
                pages.append(PageText(page_number=p.page_number, text=res.text, words=None, lines=None, blocks=None, tables=None))

    elif ext in {"jpg", "jpeg", "png", "bmp", "tif", "tiff"}:
        ingested = image_to_page(file_bytes)
        p = ingested[0]
        prep = preprocess_image(p.image, request_id=request_id, page_number=1, enable=preprocess)
        cls = classify_from_signals(blur_var=prep.blur_var, contrast=prep.contrast, edge_density=prep.edge_density)
        classifications.append(cls)
        profile = _profile_for_category(cls.category)

        if enable_layout:
            res = _ENGINE.ocr(prep.image, with_words=True, profile=profile)
            words = res.words or []
            lines = layout_service.words_to_lines(words) if words else None
            blocks = layout_service.lines_to_blocks(lines) if lines else None
            tables = layout_service.detect_tables_from_lines(lines) if lines else None
            pages = [PageText(page_number=1, text=res.text, words=words, lines=lines, blocks=blocks, tables=tables)]
        else:
            res = _ENGINE.ocr(prep.image, with_words=False, profile=profile)
            pages = [PageText(page_number=1, text=res.text, words=None, lines=None, blocks=None, tables=None)]

    elif ext == "docx":
        pages = _extract_from_docx(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: .{ext or 'unknown'}")

    if enable_layout:
        try:
            layout_service.tag_headers_footers(pages)
        except Exception:
            pass
        pages = normalize_pages(pages)

    full_text = "\n\n".join(p.text for p in pages)
    processing_time_ms = int((time.time() - start) * 1000)

    if not zero_retention:
        file_service.save_unique_by_name(filename, file_bytes)
    else:
        file_service.delete_if_exists(filename)

    if classifications:
        best = max(classifications, key=lambda c: c.confidence)
        classification_meta = {
            "category": best.category,
            "confidence": float(best.confidence),
            "signals": best.signals,
        }
    else:
        classification_meta = {"category": "unknown", "confidence": 0.0, "signals": {}}

    return OCRResponse(
        job_id=job_id,
        status="success",
        document_type=document_type,
        pages=pages,
        full_text=full_text,
        metadata={
            "file_name": filename,
            "file_type": ext,
            "num_pages": len(pages),
            "processing_time_ms": processing_time_ms,
            "engine": _ENGINE.name,
            "engine_profile": _profile_for_category(classification_meta["category"]),
            "zero_retention": bool(zero_retention),
            "enable_layout": bool(enable_layout),
            "preprocess": preprocess if preprocess is not None else bool(settings.PREPROCESS_ENABLE),
            "classification": classification_meta,
            "request_id": request_id,
            "pipeline_version": "v1",
        },
    )
