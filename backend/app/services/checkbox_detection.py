from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import cv2
from PIL import Image

from app.utils.geometry import bbox_to_tuple


@dataclass
class Checkbox:
    bbox: Tuple[int, int, int, int]
    checked: bool
    score: float  # ink ratio inside


def _pil_to_gray(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("L"))


def detect_checkboxes(page_image: Image.Image) -> List[Checkbox]:
    """Detect small square checkboxes and whether they are checked.

    Works best on scanned forms (not UI screenshots).
    """
    gray = _pil_to_gray(page_image)

    # binarize
    bin_inv = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 35, 10
    )

    # find contours
    cnts, _ = cv2.findContours(bin_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape[:2]
    out: List[Checkbox] = []

    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < 10 or bh < 10:
            continue
        if bw * bh > 0.02 * w * h:
            continue
        ar = bw / float(bh)
        if ar < 0.7 or ar > 1.3:
            continue
        area = bw * bh
        if area < 120 or area > 4000:
            continue

        # square-ish
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.06 * peri, True)
        if len(approx) < 4:
            continue

        # compute ink inside (checked mark) by masking border
        pad = max(1, int(min(bw, bh) * 0.2))
        x1 = x + pad
        y1 = y + pad
        x2 = x + bw - pad
        y2 = y + bh - pad
        if x2 <= x1 or y2 <= y1:
            continue

        inner = bin_inv[y1:y2, x1:x2]
        ink = float(np.count_nonzero(inner)) / float(inner.size + 1e-6)
        checked = ink > 0.08  # threshold tuned for common ticks
        out.append(Checkbox(bbox=(x, y, x + bw, y + bh), checked=checked, score=ink))

    # de-dup very overlapping boxes
    out_sorted = sorted(out, key=lambda cb: (cb.bbox[1], cb.bbox[0]))
    merged: List[Checkbox] = []
    for cb in out_sorted:
        if not merged:
            merged.append(cb)
            continue
        x1, y1, x2, y2 = cb.bbox
        mx1, my1, mx2, my2 = merged[-1].bbox
        if abs(x1 - mx1) < 3 and abs(y1 - my1) < 3 and abs(x2 - mx2) < 3 and abs(y2 - my2) < 3:
            # keep the higher score
            if cb.score > merged[-1].score:
                merged[-1] = cb
        else:
            merged.append(cb)
    return merged


def attach_checkboxes_to_blocks(blocks: List[Dict[str, Any]], checkboxes: List[Checkbox]) -> List[Dict[str, Any]]:
    """Attach checkbox markers to nearest text block on the same line (to the right).

    Adds:
      - block['checkbox'] = {'checked': bool, 'bbox':[...], 'score': float}
      - block['type'] becomes 'list_item' if it was paragraph
      - block['marker'] becomes '[x]' or '[ ]' (downstream markdown renders task list)
    """
    if not blocks or not checkboxes:
        return blocks

    out: List[Dict[str, Any]] = [dict(b) for b in blocks]

    for cb in checkboxes:
        cx1, cy1, cx2, cy2 = cb.bbox
        ccy = (cy1 + cy2) // 2

        best_i: Optional[int] = None
        best_dist = 1e18

        for i, b in enumerate(out):
            bb = bbox_to_tuple(b.get("bbox"))
            if bb is None:
                continue
            x1, y1, x2, y2 = bb
            by = (y1 + y2) // 2

            # same line-ish
            if abs(by - ccy) > max(12, (y2 - y1) // 2):
                continue

            # checkbox should be left of text
            if cx2 > x2:
                continue

            dx = (x1 - cx2) if cx2 <= x1 else 0
            dy = abs(by - ccy)
            dist = dx * dx + dy * dy

            if dist < best_dist:
                best_dist = dist
                best_i = i

        if best_i is not None and best_dist < (3000 * 3000):
            b = out[best_i]
            b["checkbox"] = {
                "checked": bool(cb.checked),
                "bbox": [cx1, cy1, cx2, cy2],
                "score": float(cb.score),
            }
            if b.get("type") in (None, "", "paragraph", "unknown"):
                b["type"] = "list_item"
            b["marker"] = "[x]" if cb.checked else "[ ]"
            out[best_i] = b

    return out
