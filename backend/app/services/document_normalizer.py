from __future__ import annotations

from typing import Any, Dict, List
import re

from app.models.document_model import DocumentModel, NormPage, NormBlock, NormLine, NormWord
from app.services.semantic_cleanup_v2 import normalize_text, split_list_marker
from app.services.routing import classify_page
from app.services.table_candidates import mark_table_candidates
from app.services.export_markdown import document_to_markdown


def _is_heading(text: str, avg_line_len: float, is_top_block: bool) -> bool:
    if not text:
        return False
    # headings are often short, possibly uppercase, and near top
    if len(text) <= max(40, int(avg_line_len * 0.8)) and (text.isupper() or is_top_block):
        return True
    return False


def normalize_document(pages: List[Dict[str, Any]], *, full_text: str) -> DocumentModel:
    norm_pages: List[NormPage] = []

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
                )
            )

        norm_pages.append(
            NormPage(
                page_number=p.get("page_number"),
                blocks=blocks,
                classification=classification,
                routing=routing_stats,
            )
        )

    full_text_norm = normalize_text(full_text)
    md = document_to_markdown([pg.model_dump() for pg in norm_pages])

    return DocumentModel(
        pages=norm_pages,
        full_text=full_text,
        full_text_normalized=full_text_norm,
        markdown=md,
        metadata={"num_pages": len(norm_pages)},
    )
