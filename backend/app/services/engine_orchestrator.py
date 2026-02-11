from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from app.core.config import settings

# Optional engines (must never crash orchestrator if missing)
try:
    from app.services.doctr_engine import doctr_ocr_page
except Exception:
    doctr_ocr_page = None  # type: ignore

try:
    from app.services.trocr_engine import trocr_ocr_crops
except Exception:
    trocr_ocr_crops = None  # type: ignore

try:
    from app.services.form_box_ocr import detect_boxed_field_regions, ocr_boxed_region
except Exception:
    detect_boxed_field_regions = None  # type: ignore
    ocr_boxed_region = None  # type: ignore

try:
    from app.services.checkbox_detection import detect_checkboxes, attach_checkboxes_to_blocks
except Exception:
    detect_checkboxes = None  # type: ignore
    attach_checkboxes_to_blocks = None  # type: ignore


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _bbox_to_tuple(bbox: Any) -> Optional[Tuple[int, int, int, int]]:
    if isinstance(bbox, dict):
        return (
            int(bbox.get("x1", 0)),
            int(bbox.get("y1", 0)),
            int(bbox.get("x2", 0)),
            int(bbox.get("y2", 0)),
        )
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        return tuple(int(v) for v in bbox)  # type: ignore
    return None


def _overlap(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = (ax2 - ax1) * (ay2 - ay1) + 1e-6
    return float(inter / area_a)


def _page_word_count(blocks: List[Dict[str, Any]]) -> int:
    n = 0
    for b in (blocks or []):
        for ln in (b.get("lines") or []):
            for w in (ln.get("words") or []):
                if isinstance(w, dict) and (w.get("text") or "").strip():
                    n += 1
    return n


def orchestrate_page_ocr(
    *,
    page_image: Image.Image,
    page_number: int,
    base_page_dict: Dict[str, Any],
    enable_doctr: Optional[bool] = None,
    enable_trocr: Optional[bool] = None,
    max_trocr_regions: int = 15,
    max_doctr_pages: int = 8,
    doctr_only_if_table_candidate: bool = True,
    enable_form_box_ocr: Optional[bool] = None,
    enable_checkbox_detection: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Region-based, non-destructive orchestration.
    IMPORTANT FIXES vs old version:
      1) TrOCR results now update block["text"] (not only text_engine) → visible everywhere.
      2) Indentation fixed → checkbox/docTR always run (not trapped under fallback).
      3) Always returns page dict → no silent None returns; errors recorded in diagnostics.
    """
    if enable_doctr is None:
        enable_doctr = bool(getattr(settings, "ENABLE_DOCTR", False))
    if enable_trocr is None:
        enable_trocr = bool(getattr(settings, "ENABLE_TROCR", False))
    if enable_form_box_ocr is None:
        enable_form_box_ocr = bool(getattr(settings, "ENABLE_FORM_BOX_OCR", False))
    if enable_checkbox_detection is None:
        enable_checkbox_detection = bool(getattr(settings, "ENABLE_CHECKBOX_DETECTION", False))

    page: Dict[str, Any] = dict(base_page_dict)
    page.setdefault("engine_usage", {})
    page["engine_usage"].setdefault("tesseract", True)

    # Deterministic visibility (no silent skips)
    page["engine_usage"]["trocr_enabled"] = bool(enable_trocr)
    page["engine_usage"]["doctr_enabled"] = bool(enable_doctr)
    page["engine_usage"]["form_box_ocr_enabled"] = bool(enable_form_box_ocr)
    page["engine_usage"]["checkbox_detection_enabled"] = bool(enable_checkbox_detection)

    page["engine_usage"]["trocr_available"] = trocr_ocr_crops is not None
    page["engine_usage"]["doctr_available"] = doctr_ocr_page is not None
    page["engine_usage"]["form_box_ocr_available"] = (
        detect_boxed_field_regions is not None and ocr_boxed_region is not None
    )
    page["engine_usage"]["checkbox_detection_available"] = (
        detect_checkboxes is not None and attach_checkboxes_to_blocks is not None
    )

    blocks: List[Dict[str, Any]] = list(page.get("blocks") or [])

    # 0) Detect boxed-field regions first (prevents forms being misrouted as tables)
    boxed_regions: List[Tuple[int, int, int, int]] = []
    if enable_form_box_ocr and detect_boxed_field_regions is not None:
        try:
            boxed_regions = detect_boxed_field_regions(page_image)
        except Exception as e:
            page.setdefault("diagnostics", {})
            page["diagnostics"]["form_box_detect_error"] = str(e)
            boxed_regions = []

    if boxed_regions:
        page.setdefault("routing", {})
        page["routing"]["boxed_field_regions"] = [list(b) for b in boxed_regions]
        page["engine_usage"]["form_box_ocr"] = True
        page["engine_usage"]["form_box_ocr_skip_reason"] = None
    else:
        page["engine_usage"]["form_box_ocr"] = False
        if not enable_form_box_ocr:
            page["engine_usage"]["form_box_ocr_skip_reason"] = "disabled"
        elif detect_boxed_field_regions is None or ocr_boxed_region is None:
            page["engine_usage"]["form_box_ocr_skip_reason"] = "engine_unavailable"
        else:
            page["engine_usage"]["form_box_ocr_skip_reason"] = "no_box_regions_detected"

    # Mark blocks overlapping boxed regions
    if boxed_regions:
        for i, b in enumerate(blocks):
            bb = _bbox_to_tuple(b.get("bbox"))
            if bb is None:
                continue
            if any(_overlap(bb, r) >= 0.35 for r in boxed_regions):
                b2 = dict(b)
                b2["form_box_region"] = True
                b2["table_candidate"] = False
                if b2.get("type") == "table_region":
                    b2["type"] = "paragraph"
                blocks[i] = b2

    # 1) Box OCR regions → attach as new blocks (non-destructive)
    if boxed_regions and ocr_boxed_region is not None:
        for r in boxed_regions[:20]:
            try:
                line = ocr_boxed_region(page_image, r)
                txt = (getattr(line, "text", "") or "").strip()
                if not txt:
                    continue
                x1, y1, x2, y2 = getattr(line, "bbox", r)
                blocks.append(
                    {
                        "type": "paragraph",
                        "text": txt,
                        "text_normalized": txt,
                        "bbox": {"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)},
                        "script": "handwritten",
                        "engine": "form_box_ocr",
                        "form_box_region": True,
                        "table_candidate": False,
                    }
                )
            except Exception as e:
                page.setdefault("diagnostics", {})
                page["diagnostics"].setdefault("form_box_ocr_errors", [])
                page["diagnostics"]["form_box_ocr_errors"].append(str(e))

    # 2) TrOCR: handwritten blocks only (excluding boxed fields)
    trocr_used = False
    if enable_trocr and trocr_ocr_crops is not None and blocks:
        crops: List[Tuple[int, int, int, int]] = []
        crop_block_indices: List[int] = []

        for i, b in enumerate(blocks):
            if (b.get("script") or "").lower() != "handwritten":
                continue
            if b.get("form_box_region"):
                continue  # handled by form_box_ocr
            bbox = _bbox_to_tuple(b.get("bbox"))
            if bbox is None:
                continue
            x1, y1, x2, y2 = bbox
            if x2 <= x1 or y2 <= y1:
                continue
            crops.append((x1, y1, x2, y2))
            crop_block_indices.append(i)
            if len(crops) >= max_trocr_regions:
                break

        if crops:
            try:
                results = trocr_ocr_crops(page_image, crops)
                for idx, txt in zip(crop_block_indices, results):
                    if txt and txt.strip():
                        t = txt.strip()

                        # Preserve original tesseract in text_engine (non-destructive),
                        # but MUST update "text" to make override actually take effect.
                        prev = (blocks[idx].get("text") or "").strip()
                        if prev:
                            blocks[idx]["text_engine"] = prev

                        blocks[idx]["engine"] = "trocr"
                        blocks[idx]["text"] = t
                        blocks[idx]["text_normalized"] = t
                        trocr_used = True
            except Exception as e:
                page.setdefault("diagnostics", {})
                page["diagnostics"]["trocr_region_error"] = str(e)

    page["engine_usage"]["trocr"] = bool(trocr_used)
    if trocr_used:
        page["engine_usage"]["trocr_skip_reason"] = None
    else:
        if not enable_trocr:
            page["engine_usage"]["trocr_skip_reason"] = "disabled"
        elif trocr_ocr_crops is None:
            page["engine_usage"]["trocr_skip_reason"] = "engine_unavailable"
        else:
            page["engine_usage"]["trocr_skip_reason"] = "no_handwritten_regions_selected"

    # 2b) TrOCR full-page fallback for cursive/freehand pages with almost no tokens
    if enable_trocr and trocr_ocr_crops is not None and not trocr_used:
        try:
            wc = _page_word_count(blocks)
            if wc < 6:
                w, h = page_image.size
                txts = trocr_ocr_crops(page_image, [(0, 0, w, h)])
                txt = (txts[0] if txts else "").strip()

                page.setdefault("routing", {})
                page["routing"]["trocr_full_page_fallback"] = {"word_count": wc}

                if txt:
                    blocks.append(
                        {
                            "type": "paragraph",
                            "text": txt,
                            "text_normalized": txt,
                            "bbox": {"x1": 0, "y1": 0, "x2": int(w), "y2": int(h)},
                            "script": "handwritten",
                            "engine": "trocr",
                            "table_candidate": False,
                        }
                    )
                    trocr_used = True
                    page["engine_usage"]["trocr"] = True
                    page["engine_usage"]["trocr_skip_reason"] = None
                else:
                    page["engine_usage"]["trocr_skip_reason"] = "ran_but_empty"
        except Exception as e:
            page.setdefault("diagnostics", {})
            page["diagnostics"]["trocr_full_page_error"] = str(e)

    # 3) Checkbox detection (attach markers)
    if enable_checkbox_detection and detect_checkboxes is not None and attach_checkboxes_to_blocks is not None:
        try:
            cbs = detect_checkboxes(page_image)
            if cbs:
                blocks = attach_checkboxes_to_blocks(blocks, cbs)
                page.setdefault("routing", {})
                page["routing"]["checkboxes_detected"] = len(cbs)
                page["engine_usage"]["checkbox_detection"] = True
            else:
                page["engine_usage"]["checkbox_detection"] = False
        except Exception as e:
            page.setdefault("diagnostics", {})
            page["diagnostics"]["checkbox_detection_error"] = str(e)
            page["engine_usage"]["checkbox_detection"] = False
    else:
        page["engine_usage"]["checkbox_detection"] = False

    # 4) docTR: layout heavy pages (avoid boxed-field forms that look like tables)
    if enable_doctr and doctr_ocr_page is not None:
        if doctr_only_if_table_candidate:
            has_candidate = any(
                (bool(b.get("table_candidate")) or (b.get("type") == "table_region"))
                and not bool(b.get("form_box_region"))
                for b in blocks
            )
        else:
            has_candidate = True

        if has_candidate and page_number <= max_doctr_pages:
            try:
                doctr_out = doctr_ocr_page(page_image)
                if doctr_out and doctr_out.get("text"):
                    page["engine_usage"]["doctr"] = True
                    page["doctr"] = doctr_out
                else:
                    page["engine_usage"]["doctr"] = False
            except Exception as e:
                page.setdefault("diagnostics", {})
                page["diagnostics"]["doctr_error"] = str(e)
                page["engine_usage"]["doctr"] = False
        else:
            page["engine_usage"]["doctr"] = False
    else:
        page["engine_usage"]["doctr"] = False

    page["blocks"] = blocks
    return page
