"""Geometry helpers.

This module provides small bbox utilities used across the OCR pipeline.
It is designed to be backward-compatible with earlier bbox shapes.

Canonical bbox tuple format throughout the pipeline:
    (x1, y1, x2, y2)

Supported input shapes:
- dict: {x1,y1,x2,y2}
- dict: {left,top,right,bottom}
- dict: {left,top,width,height}
- list/tuple: [x1,y1,x2,y2]
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple


def sort_boxes_reading_order(boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort boxes by reading order using canonical bbox list/tuple at boxes[i]['bbox']."""
    return sorted(boxes, key=lambda b: (b["bbox"][1], b["bbox"][0]))


def merge_boxes(boxes: List[Dict[str, Any]]) -> List[int]:
    """Merge list of boxes that contain bbox list/tuple into one bbox list."""
    x1 = min(b["bbox"][0] for b in boxes)
    y1 = min(b["bbox"][1] for b in boxes)
    x2 = max(b["bbox"][2] for b in boxes)
    y2 = max(b["bbox"][3] for b in boxes)
    return [int(x1), int(y1), int(x2), int(y2)]


def bbox_to_tuple(bbox: Any) -> Optional[Tuple[int, int, int, int]]:
    """Best-effort conversion to (x1,y1,x2,y2). Returns None if not possible."""
    try:
        if isinstance(bbox, dict):
            # canonical
            if all(k in bbox for k in ("x1", "y1", "x2", "y2")):
                return (int(float(bbox.get("x1", 0))), int(float(bbox.get("y1", 0))), int(float(bbox.get("x2", 0))), int(float(bbox.get("y2", 0))))

            # legacy
            if all(k in bbox for k in ("left", "top", "right", "bottom")):
                l = int(float(bbox.get("left", 0)))
                t = int(float(bbox.get("top", 0)))
                r = int(float(bbox.get("right", 0)))
                b = int(float(bbox.get("bottom", 0)))
                return (l, t, r, b)

            # tesseract-like
            if all(k in bbox for k in ("left", "top", "width", "height")):
                l = int(float(bbox.get("left", 0)))
                t = int(float(bbox.get("top", 0)))
                w = int(float(bbox.get("width", 0)))
                h = int(float(bbox.get("height", 0)))
                return (l, t, l + w, t + h)

        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            return (int(float(bbox[0])), int(float(bbox[1])), int(float(bbox[2])), int(float(bbox[3])))

    except Exception:
        return None

    return None


def normalize_bbox_dict(bbox: Any) -> Dict[str, int]:
    """Return bbox as a dict containing BOTH canonical and legacy keys.

    Output keys:
      - x1,y1,x2,y2
      - left,top,right,bottom

    If bbox cannot be parsed, returns zeros.
    """
    t = bbox_to_tuple(bbox)
    if t is None:
        x1 = y1 = x2 = y2 = 0
    else:
        x1, y1, x2, y2 = t

    return {
        "x1": int(x1),
        "y1": int(y1),
        "x2": int(x2),
        "y2": int(y2),
        "left": int(x1),
        "top": int(y1),
        "right": int(x2),
        "bottom": int(y2),
    }


def clamp_bbox(
    bbox: Tuple[int, int, int, int],
    *,
    width: int,
    height: int,
) -> Tuple[int, int, int, int]:
    """Clamp bbox to image bounds."""
    x1, y1, x2, y2 = bbox
    x1 = max(0, min(int(x1), int(width)))
    y1 = max(0, min(int(y1), int(height)))
    x2 = max(0, min(int(x2), int(width)))
    y2 = max(0, min(int(y2), int(height)))
    return (x1, y1, x2, y2)


def pad_bbox(
    bbox: Tuple[int, int, int, int],
    *,
    pad: int,
    width: int,
    height: int,
) -> Tuple[int, int, int, int]:
    """Pad bbox by `pad` pixels and clamp to bounds."""
    x1, y1, x2, y2 = bbox
    return clamp_bbox((x1 - pad, y1 - pad, x2 + pad, y2 + pad), width=width, height=height)
