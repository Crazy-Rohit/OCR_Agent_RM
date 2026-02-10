from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

# Local engines are optional. If missing deps, we fall back safely.
try:
    from app.services.doctr_engine import doctr_ocr_page
except Exception:
    doctr_ocr_page = None  # type: ignore

try:
    from app.services.trocr_engine import trocr_ocr_crops
except Exception:
    trocr_ocr_crops = None  # type: ignore

# Form boxed-field OCR (grid boxes) - optional but recommended for insurance/PA forms
try:
    from app.services.form_box_ocr import detect_boxed_field_regions, ocr_boxed_region
except Exception:
    detect_boxed_field_regions = None  # type: ignore
    ocr_boxed_region = None  # type: ignore

# Checkbox detection (task-list / form checkboxes)
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


def _bbox_to_tuple(bbox: Any) -> Optional[Tuple[int,int,int,int]]:
    if isinstance(bbox, dict):
        return (int(bbox.get("x1",0)), int(bbox.get("y1",0)), int(bbox.get("x2",0)), int(bbox.get("y2",0)))
    if isinstance(bbox, (list,tuple)) and len(bbox)==4:
        return tuple(int(v) for v in bbox)  # type: ignore
    return None


def _overlap(a: Tuple[int,int,int,int], b: Tuple[int,int,int,int]) -> float:
    ax1,ay1,ax2,ay2=a; bx1,by1,bx2,by2=b
    ix1=max(ax1,bx1); iy1=max(ay1,by1); ix2=min(ax2,bx2); iy2=min(ay2,by2)
    if ix2<=ix1 or iy2<=iy1:
        return 0.0
    inter=(ix2-ix1)*(iy2-iy1)
    area_a=(ax2-ax1)*(ay2-ay1) + 1e-6
    return float(inter/area_a)


def orchestrate_page_ocr(
    *,
    page_image: Image.Image,
    page_number: int,
    base_page_dict: Dict[str, Any],
    enable_doctr: Optional[bool] = None,
    enable_trocr: Optional[bool] = None,
    max_trocr_regions: int = 12,
    max_doctr_pages: int = 6,
    doctr_only_if_table_candidate: bool = True,
    enable_form_box_ocr: Optional[bool] = None,
    enable_checkbox_detection: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Region-based non-destructive orchestration:
      - Uses existing base_page_dict (built from Tesseract pipeline).
      - Adds region-specific refinements:
          * Boxed form fields (grid boxes): per-cell OCR + row reconstruction
          * TrOCR: freehand handwritten blocks (not boxed)
          * docTR: optional layout-heavy pages (typically table-heavy)
          * Checkbox detection: attaches [x]/[ ] markers to nearby blocks
      - Never crashes if optional deps missing.
    """
    if enable_doctr is None:
        enable_doctr = _env_bool("ENABLE_DOCTR", False)
    if enable_trocr is None:
        enable_trocr = _env_bool("ENABLE_TROCR", False)
    if enable_form_box_ocr is None:
        enable_form_box_ocr = _env_bool("ENABLE_FORM_BOX_OCR", False)
    if enable_checkbox_detection is None:
        enable_checkbox_detection = _env_bool("ENABLE_CHECKBOX_DETECTION", False)

    page = dict(base_page_dict)
    page.setdefault("engine_usage", {})
    page["engine_usage"].setdefault("tesseract", True)

    blocks: List[Dict[str, Any]] = list(page.get("blocks") or [])

    # 0) Detect boxed-field regions first (IMPORTANT: prevents table misclassification on forms)
    boxed_regions: List[Tuple[int,int,int,int]] = []
    if enable_form_box_ocr and detect_boxed_field_regions is not None:
        try:
            boxed_regions = detect_boxed_field_regions(page_image)
        except Exception:
            boxed_regions = []

    if boxed_regions:
        page.setdefault("routing", {})
        page["routing"]["boxed_field_regions"] = [list(b) for b in boxed_regions]
        page["engine_usage"]["form_box_ocr"] = True
    else:
        page["engine_usage"]["form_box_ocr"] = False

    # If a block overlaps a boxed region strongly, mark it so downstream table-candidate logic can ignore it
    if boxed_regions:
        for i, b in enumerate(blocks):
            bb = _bbox_to_tuple(b.get("bbox"))
            if bb is None:
                continue
            if any(_overlap(bb, r) >= 0.35 for r in boxed_regions):
                b2 = dict(b)
                b2["form_box_region"] = True
                # boxed fields are NOT tables
                b2["table_candidate"] = False
                if b2.get("type") == "table_region":
                    b2["type"] = "paragraph"
                blocks[i] = b2

    # 1) Box OCR on each boxed region and attach results as dedicated blocks (non-destructive)
    if boxed_regions and ocr_boxed_region is not None:
        for r in boxed_regions[:20]:
            try:
                line = ocr_boxed_region(page_image, r)
                txt = (line.text or "").strip()
                if not txt:
                    continue
                x1,y1,x2,y2 = line.bbox
                blocks.append({
                    "type": "paragraph",
                    "text": txt,
                    "text_normalized": txt,
                    "bbox": {"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)},
                    "script": "handwritten",
                    "engine": "form_box_ocr",
                    "form_box_region": True,
                    "table_candidate": False,
                })
            except Exception:
                continue

    # 2) TrOCR: handwritten blocks only (EXCLUDING boxed-field regions)
    trocr_used = False
    if enable_trocr and trocr_ocr_crops is not None and blocks:
        crops: List[Tuple[int, int, int, int]] = []
        crop_block_indices: List[int] = []
        for i, b in enumerate(blocks):
            script = (b.get("script") or "").lower()
            if script != "handwritten":
                continue
            if b.get("form_box_region"):
                # boxed fields handled by form_box_ocr, not TrOCR
                continue
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
            results = trocr_ocr_crops(page_image, crops)
            for idx, txt in zip(crop_block_indices, results):
                if txt and txt.strip():
                    blocks[idx]["engine"] = "trocr"
                    blocks[idx]["text_engine"] = txt.strip()
                    blocks[idx]["text_normalized"] = txt.strip()
                    trocr_used = True

    page["engine_usage"]["trocr"] = bool(trocr_used)

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
        except Exception:
            page["engine_usage"]["checkbox_detection"] = False
    else:
        page["engine_usage"]["checkbox_detection"] = False

    # 4) docTR: layout heavy pages (or table-candidate pages)
    # IMPORTANT: boxed-field forms can look like tables. docTR runs only if there are REAL table candidates.
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
            doctr_out = doctr_ocr_page(page_image)
            if doctr_out and doctr_out.get("text"):
                page["engine_usage"]["doctr"] = True
                page["doctr"] = doctr_out
            else:
                page["engine_usage"]["doctr"] = False
        else:
            page["engine_usage"]["doctr"] = False
    else:
        page["engine_usage"]["doctr"] = False

    page["blocks"] = blocks
    return page
