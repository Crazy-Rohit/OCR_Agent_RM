from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import cv2
from PIL import Image


def detect_checkboxes(
    page_image: Image.Image,
    *,
    min_size_px: int = 10,
    max_size_px: int = 120,
) -> List[Dict[str, Any]]:
    """
    Detect checkbox-like square boxes on a page image.
    Returns list of {bbox:[x1,y1,x2,y2], state:"checked"|"unchecked", score:float}.
    Best-effort heuristic (works well for forms).
    """
    # Convert to grayscale numpy
    img = np.array(page_image.convert("L"))
    h, w = img.shape[:2]

    # Adaptive threshold to handle uneven lighting
    # Use odd blockSize; tune for typical scanned forms
    block = int(max(31, (min(h, w) // 40) | 1))
    thr = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY_INV, block, 7)

    # Mild morph to connect box borders
    k = max(1, min(h, w) // 500)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
    thr = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes: List[Dict[str, Any]] = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw < min_size_px or bh < min_size_px or bw > max_size_px or bh > max_size_px:
            continue

        # Must be roughly square
        ar = bw / float(bh + 1e-6)
        if ar < 0.75 or ar > 1.33:
            continue

        area = bw * bh
        # Relative area sanity
        if area < 80 or area > (max_size_px * max_size_px):
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
        if len(approx) < 4 or len(approx) > 8:
            continue

        # Border thickness estimate: if box is just a filled square, skip
        # Compute edge pixel ratio inside bbox border band
        crop = thr[y:y+bh, x:x+bw]
        if crop.size == 0:
            continue

        # Inner region (exclude border)
        pad = max(2, int(min(bw, bh) * 0.2))
        inner = crop[pad:bh-pad, pad:bw-pad]
        if inner.size == 0:
            continue

        # Determine checkedness: how much ink inside inner area
        ink_ratio = float(np.count_nonzero(inner)) / float(inner.size)
        state = "checked" if ink_ratio >= 0.06 else "unchecked"

        boxes.append({
            "bbox": [int(x), int(y), int(x + bw), int(y + bh)],
            "state": state,
            "score": round(ink_ratio, 4),
        })

    # Sort top-to-bottom, left-to-right
    boxes.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
    return boxes


def attach_checkboxes_to_blocks(
    page_dict: Dict[str, Any],
    checkboxes: List[Dict[str, Any]],
    *,
    x_gap_px: int = 140,
    y_iou_min: float = 0.12,
) -> Dict[str, Any]:
    """
    Attach checkbox markers to nearest blocks (list item conversion).
    Adds:
      page_dict["annotations"]["checkboxes"]
      block["checkbox"] = {state, bbox, score}
      block["type"]="list_item" and block["marker"]="[x]" or "[ ]" when matched.
    """
    blocks = page_dict.get("blocks") or []
    ann = page_dict.get("annotations") or {}
    ann["checkboxes"] = checkboxes
    page_dict["annotations"] = ann

    def block_bbox(b: Dict[str, Any]) -> Optional[Tuple[int,int,int,int]]:
        bb = b.get("bbox") or {}
        if isinstance(bb, dict):
            x1 = bb.get("x1"); y1 = bb.get("y1"); x2 = bb.get("x2"); y2 = bb.get("y2")
            if all(v is not None for v in (x1,y1,x2,y2)):
                return int(x1), int(y1), int(x2), int(y2)
        if isinstance(bb, list) and len(bb) == 4:
            return int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])
        return None

    def y_iou(a: Tuple[int,int,int,int], b: Tuple[int,int,int,int]) -> float:
        ay1, ay2 = a[1], a[3]
        by1, by2 = b[1], b[3]
        inter = max(0, min(ay2, by2) - max(ay1, by1))
        union = max(1, (ay2-ay1) + (by2-by1) - inter)
        return inter / union

    for cb in checkboxes:
        cbx1, cby1, cbx2, cby2 = cb["bbox"]
        cb_box = (cbx1, cby1, cbx2, cby2)
        best_i = None
        best_score = 0.0

        for i, b in enumerate(blocks):
            bb = block_bbox(b)
            if not bb:
                continue
            # checkbox should be left of text block
            if bb[0] < cbx2:
                continue
            gap = bb[0] - cbx2
            if gap > x_gap_px:
                continue
            yi = y_iou(bb, cb_box)
            if yi < y_iou_min:
                continue
            score = yi * (1.0 - min(gap / max(1, x_gap_px), 1.0))
            if score > best_score:
                best_score = score
                best_i = i

        if best_i is not None:
            b = blocks[best_i]
            marker = "[x]" if cb["state"] == "checked" else "[ ]"
            b["checkbox"] = {"state": cb["state"], "bbox": cb["bbox"], "score": cb.get("score")}
            # Convert to list item if not already
            if b.get("type") not in {"heading", "table_region"}:
                b["type"] = "list_item"
                b["marker"] = marker

    page_dict["blocks"] = blocks
    return page_dict
