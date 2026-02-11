from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional
from PIL import Image

try:
    import cv2  # type: ignore
except Exception:
    cv2 = None  # type: ignore
import numpy as np
import pytesseract
from typing import List, Dict, Any

@dataclass
class BoxLineResult:
    text: str
    bbox: Tuple[int, int, int, int]
    confidence: float = 0.0
    boxes: Optional[list] = None


def _pil_to_bgr(img: Image.Image) -> np.ndarray:
    arr = np.array(img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def detect_boxed_field_regions(page_image: Image.Image) -> List[Tuple[int, int, int, int]]:
    """
    Detect likely boxed-grid handwriting regions (rows/strips of small boxes).
    Works with connected grid lines common in insurance/PA forms.
    Returns list of region bboxes (x1,y1,x2,y2).
    """
    bgr = _pil_to_bgr(page_image)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # Enhance lines
    bin_img = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 21, 7
    )

    # Extract horizontal + vertical lines
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 35))
    horiz = cv2.morphologyEx(bin_img, cv2.MORPH_OPEN, h_kernel, iterations=1)
    vert = cv2.morphologyEx(bin_img, cv2.MORPH_OPEN, v_kernel, iterations=1)
    grid = cv2.bitwise_or(horiz, vert)

    # Find large grid-like contours (rows/areas)
    contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape[:2]
    regions: List[Tuple[int,int,int,int]] = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < int(0.35 * w):
            continue
        # typical boxed rows are not very tall; allow some slack
        if ch < 18 or ch > int(0.28 * h):
            continue
        # Reject header/footer full-width rules
        if cw > int(0.95 * w) and ch < 30:
            continue

        pad = 6
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(w, x + cw + pad)
        y2 = min(h, y + ch + pad)
        regions.append((x1, y1, x2, y2))

    # Merge overlapping regions vertically (same form section)
    regions = sorted(regions, key=lambda r: (r[1], r[0]))
    merged: List[Tuple[int,int,int,int]] = []
    for r in regions:
        if not merged:
            merged.append(r); continue
        lx1, ly1, lx2, ly2 = merged[-1]
        x1,y1,x2,y2 = r
        # if vertical overlap/adjacency and similar horizontal span, merge
        if y1 <= ly2 + 12 and (min(lx2,x2) - max(lx1,x1)) > 0.5 * min(lx2-lx1, x2-x1):
            merged[-1] = (min(lx1,x1), min(ly1,y1), max(lx2,x2), max(ly2,y2))
        else:
            merged.append(r)

    # Return top N (forms usually have few)
    return merged[:20]


def ocr_boxed_region(page_image: Image.Image, region_bbox: Tuple[int,int,int,int]) -> BoxLineResult:
    """
    OCR a boxed-grid region. Uses existing extract_form_box_text on cropped region.
    Returns BoxLineResult with .text and .bbox (for orchestrator).
    """
    x1,y1,x2,y2 = region_bbox
    crop = page_image.crop((x1,y1,x2,y2))
    bgr = _pil_to_bgr(crop)
    out = extract_form_box_text(bgr)
    txt = (out.get("text") or "").strip()
    conf = float(out.get("confidence") or 0.0) if isinstance(out.get("confidence"), (int,float)) else 0.0
    boxes = out.get("boxes") if isinstance(out.get("boxes"), list) else None
    return BoxLineResult(text=txt, bbox=(x1,y1,x2,y2), confidence=conf, boxes=boxes)




def extract_form_box_text(image_bgr: np.ndarray) -> Dict[str, Any]:
    """
    Extract text from boxed (grid-based) handwritten form fields.
    Returns:
      {
        "text": str,
        "boxes": [ {bbox, char} ],
        "form_box_region": True
      }
    """

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)

    # 1. Detect grid lines (actual boxes)
    bin_img = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY_INV,
        15, 3
    )

    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))

    horiz = cv2.morphologyEx(bin_img, cv2.MORPH_OPEN, kernel_h)
    vert = cv2.morphologyEx(bin_img, cv2.MORPH_OPEN, kernel_v)

    grid = cv2.add(horiz, vert)

    # 2. Find box contours from grid
    contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    H, W = gray.shape

    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w < 15 or h < 15:
            continue
        if w > W * 0.2 or h > H * 0.15:
            continue
        boxes.append((x, y, w, h))

    if len(boxes) < 4:
        return {"form_box_region": False}

    # 3. Sort boxes left-to-right, top-to-bottom
    boxes = sorted(boxes, key=lambda b: (b[1] // 20, b[0]))

    chars = []
    text_out = ""

    for (x, y, w, h) in boxes:
        pad = 2
        roi = gray[y+pad:y+h-pad, x+pad:x+w-pad]
        if roi.size == 0:
            continue

        roi = cv2.resize(roi, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        _, roi_bin = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        char = pytesseract.image_to_string(
            roi_bin,
            config="--psm 10 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        ).strip()

        if len(char) == 1:
            text_out += char
            chars.append({
                "char": char,
                "bbox": [x, y, x + w, y + h]
            })
        else:
            text_out += " "

    return {
        "form_box_region": True,
        "text": text_out.strip(),
        "chars": chars
    }
