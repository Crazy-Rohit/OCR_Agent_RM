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


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


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
) -> Dict[str, Any]:
    """
    Non-destructive orchestration:
      - Uses existing base_page_dict (typically built from Tesseract pipeline).
      - Optionally refines/overrides text for specific regions via:
          * TrOCR: handwritten crops only (block bboxes)
          * docTR: layout-heavy pages (optional)
      - Adds metadata about engine usage; never crashes if deps missing.
    """
    if enable_doctr is None:
        enable_doctr = _env_bool("ENABLE_DOCTR", False)
    if enable_trocr is None:
        enable_trocr = _env_bool("ENABLE_TROCR", False)

    page = dict(base_page_dict)
    page.setdefault("engine_usage", {})
    page["engine_usage"].setdefault("tesseract", True)

    blocks = page.get("blocks") or []

    # 1) TrOCR: handwritten blocks only
    trocr_used = False
    if enable_trocr and trocr_ocr_crops is not None and blocks:
        crops: List[Tuple[int, int, int, int]] = []
        crop_block_indices: List[int] = []
        for i, b in enumerate(blocks):
            script = (b.get("script") or "").lower()
            if script != "handwritten":
                continue
            bbox = b.get("bbox")
            if isinstance(bbox, dict):
                x1 = int(bbox.get("x1", 0)); y1 = int(bbox.get("y1", 0))
                x2 = int(bbox.get("x2", 0)); y2 = int(bbox.get("y2", 0))
                bbox = [x1, y1, x2, y2]
            if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
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

    page["blocks"] = blocks
    page["engine_usage"]["trocr"] = bool(trocr_used)

    # 2) docTR: layout heavy pages (or table-candidate pages)
    if enable_doctr and doctr_ocr_page is not None:
        if doctr_only_if_table_candidate:
            has_candidate = any(bool(b.get("table_candidate")) or (b.get("type") == "table_region") for b in blocks)
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

    return page
