from __future__ import annotations

from typing import Any, Dict, List
import re

from app.models.document_model import (
    DocumentModel,
    NormPage,
    NormBlock,
    NormLine,
    NormWord,
    NormTable,
    NormTableCell,
)
from app.services.semantic_cleanup_v2 import normalize_text, split_list_marker
from app.services.routing import classify_page
from app.services.handwriting_detection import detect_handwriting_block, aggregate_page_script
from app.services.table_candidates import mark_table_candidates
try:
    from app.services.table_extraction import extract_tables_from_blocks
except Exception:  # pragma: no cover
    extract_tables_from_blocks = None  # type: ignore
from app.services.export_markdown import document_to_markdown
from app.services.export_html import document_to_html
from app.services.chunking import chunk_document


def _is_heading(text: str, avg_line_len: float, is_top_block: bool) -> bool:
    if not text:
        return False
    # headings are often short, possibly uppercase, and near top
    if len(text) <= max(40, int(avg_line_len * 0.8)) and (text.isupper() or is_top_block):
        return True
    return False


def normalize_document(pages: List[Dict[str, Any]], *, full_text: str) -> DocumentModel:
    norm_pages: List[NormPage] = []
    norm_tables: List[NormTable] = []

    for p in pages:
        page_words = p.get("words") or []
        classification, routing_stats = classify_page(page_words)

        raw_blocks = p.get("blocks") or []
        # pre-mark table candidates on raw blocks dicts (safe, doesn't assume models)
        raw_blocks = mark_table_candidates(raw_blocks)

        # estimate typical line length
        line_lens = []
        for b in raw_blocks:
            for ln in (b.get("lines") or []):
                t = (ln.get("text") or "").strip()
                if t:
                    line_lens.append(len(t))
        avg_line_len = (sum(line_lens) / len(line_lens)) if line_lens else 60.0

        blocks: List[NormBlock] = []
        block_scripts: List[str] = []
        for bi, b in enumerate(raw_blocks):
            block_text = (b.get("text") or "").strip()
            block_text_norm = normalize_text(block_text)

            btype = b.get("type") or "paragraph"
            marker, list_rest = split_list_marker(block_text_norm.split("\n", 1)[0] if block_text_norm else "")

            # heading detection (override only if not table_region)
            if btype != "table_region" and _is_heading(block_text_norm, avg_line_len, is_top_block=(bi == 0)):
                btype = "heading"

            # list item detection (single-line list blocks or bullet-like starts)
            if btype not in {"heading", "table_region"} and marker:
                btype = "list_item"

            # Build normalized lines/words
            lines: List[NormLine] = []
            for ln in (b.get("lines") or []):
                w_objs: List[NormWord] = []
                for w in (ln.get("words") or []):
                    w_objs.append(
                        NormWord(
                            text=(w.get("text") or ""),
                            bbox=w.get("bbox"),
                            confidence=w.get("confidence"),
                        )
                    )
                lines.append(NormLine(text=normalize_text(ln.get("text") or ""), words=w_objs))

            # decide level heuristically
            level = 1 if btype == "heading" else 0

            # If list item, prefer first-line rest (marker removed) as text
            if btype == "list_item":
                # Replace first line marker only; keep remaining lines appended
                first_line, *rest_lines = block_text_norm.splitlines()
                _, first_rest = split_list_marker(first_line)
                combined = "\n".join([first_rest] + rest_lines).strip()
                block_text_norm = combined

            # Phase 4.2: handwriting detection (block-level, non-destructive)
            script, hw_score, hw_signals = detect_handwriting_block({
                "lines": [ln.model_dump() for ln in lines],
                "bbox": b.get("bbox") or {},
            })
            block_scripts.append(script)

            blocks.append(
                NormBlock(
                    type=btype,
                    text=block_text,
                    text_normalized=block_text_norm,
                    lines=lines,
                    bbox=b.get("bbox") or {},
                    level=level,
                    marker=marker,
                    table_candidate=bool(b.get("table_candidate")),
                    script=script,
                    handwriting_score=hw_score,
                    handwriting_signals=hw_signals,
                    checkbox=b.get("checkbox"),
                )
            )

        # Phase 4.1: true table extraction (non-destructive)
        if extract_tables_from_blocks is not None:
            extracted = extract_tables_from_blocks([blk.model_dump() for blk in blocks])
        else:
            extracted = []
        for t in extracted:
            cells = [
                NormTableCell(
                    row=int(c.get("row") or 0),
                    col=int(c.get("col") or 0),
                    text=(c.get("text") or ""),
                    bbox=c.get("bbox"),
                    confidence=c.get("confidence"),
                )
                for c in (t.get("cells") or [])
            ]
            norm_tables.append(
                NormTable(
                    page_number=p.get("page_number"),
                    source_block_index=t.get("source_block_index"),
                    bbox=t.get("bbox"),
                    n_rows=int(t.get("n_rows") or 0),
                    n_cols=int(t.get("n_cols") or 0),
                    cells=cells,
                    method=t.get("method") or "bbox_grid_heuristic",
                    score=t.get("score"),
                )
            )

        # Phase 4.2: page-level script aggregation (safe override when strong)
        page_script, page_script_stats = aggregate_page_script(block_scripts)
        # Keep the original classify_page result unless handwriting strongly indicates otherwise.
        if page_script in {"handwritten", "mixed"}:
            classification = page_script
        routing_stats = {**(routing_stats or {}), **{"page_script": page_script, **page_script_stats}}

        norm_pages.append(
            NormPage(
                page_number=p.get("page_number"),
                blocks=blocks,
                classification=classification,
                routing=routing_stats,
                annotations=p.get("annotations") or {},
            )
        )

    full_text_norm = normalize_text(full_text)
    md = document_to_markdown([pg.model_dump() for pg in norm_pages], tables=[t.model_dump() for t in norm_tables])

    return DocumentModel(
        pages=norm_pages,
        tables=norm_tables,
        full_text=full_text,
        full_text_normalized=full_text_norm,
        markdown=md,
        metadata={"num_pages": len(norm_pages)},
    )

# NOTE: Phase 4 fast-pack integration (tables + html + chunks)
