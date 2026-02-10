from __future__ import annotations

"""Form box OCR (grid / boxed handwriting).

Targets scanned forms where values are written inside small boxes/cells.

Approach (fast, heuristic):
1) Crop region, binarize.
2) Detect horizontal/vertical lines via morphology and mask them out.
3) Find small rectangular contours (boxes/cells).
4) Group boxes into rows, sort left->right.
5) OCR each cell with Tesseract in single-character mode (PSM 10).

This is designed to be *safe*:
- If detection fails, returns None so caller can fall back.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import cv2
from PIL import Image
import pytesseract


@dataclass
class BoxOCRResult:
    text: str
    lines: List[Dict[str, Any]]  # canonical block lines structure
    words: List[Dict[str, Any]]  # flattened words
    debug: Dict[str, Any]


def _pil_to_gray_np(img: Image.Image) -> np.ndarray:
    arr = np.array(img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)


def _binarize(gray: np.ndarray) -> np.ndarray:
    # robust for uneven lighting
    return cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        10,
    )


def _remove_grid_lines(bw_inv: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Remove horizontal/vertical lines from a binary-inverted image."""
    h, w = bw_inv.shape[:2]

    # Horizontal lines
    horiz = bw_inv.copy()
    horizontalsize = max(10, w // 40)
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (horizontalsize, 1))
    horiz = cv2.erode(horiz, h_kernel, iterations=1)
    horiz = cv2.dilate(horiz, h_kernel, iterations=1)

    # Vertical lines
    vert = bw_inv.copy()
    verticalsize = max(10, h // 40)
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, verticalsize))
    vert = cv2.erode(vert, v_kernel, iterations=1)
    vert = cv2.dilate(vert, v_kernel, iterations=1)

    grid = cv2.bitwise_or(horiz, vert)
    no_grid = cv2.bitwise_and(bw_inv, cv2.bitwise_not(grid))

    dbg = {
        "horiz_kernel": [int(horizontalsize), 1],
        "vert_kernel": [1, int(verticalsize)],
        "grid_pixels": int(np.sum(grid > 0)),
    }
    return no_grid, dbg


def _find_cell_boxes(bw_inv_no_grid: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """Return candidate cell rectangles (x1,y1,x2,y2) in crop coords."""
    contours, _ = cv2.findContours(bw_inv_no_grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: List[Tuple[int, int, int, int]] = []
    h, w = bw_inv_no_grid.shape[:2]

    # size heuristics tuned for typical form grids
    min_side = max(8, min(h, w) // 80)
    max_side = max(18, min(h, w) // 6)

    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < min_side or bh < min_side:
            continue
        if bw > max_side or bh > max_side:
            continue

        # prefer near-square-ish boxes (but allow rectangles for some forms)
        ar = bw / float(bh + 1e-6)
        if ar < 0.45 or ar > 2.2:
            continue

        # ignore very filled blobs (likely letters), keep box-like boundaries
        area = cv2.contourArea(c)
        rect_area = float(bw * bh)
        fill = area / (rect_area + 1e-6)
        if fill > 0.65:
            continue

        boxes.append((x, y, x + bw, y + bh))

    # Deduplicate / merge near-identical boxes
    boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
    merged: List[Tuple[int, int, int, int]] = []
    for b in boxes:
        if not merged:
            merged.append(b)
            continue
        x1, y1, x2, y2 = b
        px1, py1, px2, py2 = merged[-1]
        if abs(x1 - px1) <= 2 and abs(y1 - py1) <= 2 and abs(x2 - px2) <= 2 and abs(y2 - py2) <= 2:
            continue
        merged.append(b)

    return merged


def _group_rows(boxes: List[Tuple[int, int, int, int]]) -> List[List[Tuple[int, int, int, int]]]:
    if not boxes:
        return []
    # cluster by y-center
    ys = [((y1 + y2) / 2.0) for (_, y1, _, y2) in boxes]
    med_h = np.median([(y2 - y1) for (_, y1, _, y2) in boxes])
    tol = max(6.0, float(med_h) * 0.6)

    rows: List[List[Tuple[int, int, int, int]]] = []
    for b, yc in sorted(zip(boxes, ys), key=lambda t: t[1]):
        placed = False
        for r in rows:
            ry = np.mean([((bb[1] + bb[3]) / 2.0) for bb in r])
            if abs(yc - ry) <= tol:
                r.append(b)
                placed = True
                break
        if not placed:
            rows.append([b])

    # sort each row left->right
    for r in rows:
        r.sort(key=lambda b: b[0])
    return rows


def _ocr_cell_char(gray_crop: np.ndarray) -> Tuple[str, Optional[float]]:
    # enlarge a bit for better OCR
    h, w = gray_crop.shape[:2]
    scale = 2 if max(h, w) < 40 else 1
    if scale != 1:
        gray_crop = cv2.resize(gray_crop, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)

    # threshold
    _, th = cv2.threshold(gray_crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    config = "--oem 1 --psm 10 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    txt = pytesseract.image_to_string(th, config=config) or ""
    txt = txt.strip()

    # try a lightweight confidence using image_to_data (single token expected)
    conf: Optional[float] = None
    try:
        data = pytesseract.image_to_data(th, output_type=pytesseract.Output.DICT, config=config)
        confs = []
        for c in data.get("conf", []) or []:
            try:
                v = float(c)
                if v >= 0:
                    confs.append(v / 100.0)
            except Exception:
                pass
        if confs:
            conf = sum(confs) / len(confs)
    except Exception:
        conf = None

    # common garbage
    if txt in {"|", "I", "l"}:
        # leave as-is; caller may join
        pass
    return txt, conf


def boxed_grid_score(region_image: Image.Image) -> float:
    """0..1 score indicating likely boxed-grid handwriting region."""
    gray = _pil_to_gray_np(region_image)
    bw = _binarize(gray)
    # detect grid presence
    no_grid, dbg = _remove_grid_lines(bw)
    boxes = _find_cell_boxes(no_grid)
    # density normalized by area
    h, w = bw.shape[:2]
    area = float(h * w)
    density = len(boxes) / max(1.0, area / 10000.0)  # boxes per 10k px
    grid_pixels = dbg.get("grid_pixels", 0)
    grid_ratio = float(grid_pixels) / max(1.0, area)

    # heuristic combine
    score = 0.0
    if len(boxes) >= 8:
        score += 0.55
    elif len(boxes) >= 4:
        score += 0.35
    if grid_ratio >= 0.015:
        score += 0.35
    elif grid_ratio >= 0.008:
        score += 0.20
    if density >= 2.0:
        score += 0.20
    elif density >= 1.0:
        score += 0.10

    return float(max(0.0, min(1.0, score)))


def ocr_boxed_region(
    *,
    page_image: Image.Image,
    bbox: Tuple[int, int, int, int],
    page_number: int,
) -> Optional[BoxOCRResult]:
    """Extract text from boxed-grid region; returns None if not confident."""

    x1, y1, x2, y2 = [int(v) for v in bbox]
    if x2 <= x1 or y2 <= y1:
        return None

    region = page_image.crop((x1, y1, x2, y2))
    score = boxed_grid_score(region)
    if score < 0.55:
        return None

    gray = _pil_to_gray_np(region)
    bw = _binarize(gray)
    no_grid, dbg_grid = _remove_grid_lines(bw)
    boxes = _find_cell_boxes(no_grid)
    rows = _group_rows(boxes)
    if not rows:
        return None

    all_words: List[Dict[str, Any]] = []
    out_lines: List[Dict[str, Any]] = []
    line_texts: List[str] = []

    for r in rows:
        chars: List[str] = []
        line_words: List[Dict[str, Any]] = []
        for (cx1, cy1, cx2, cy2) in r:
            # inset crop to avoid borders
            pad = 2
            ix1 = max(cx1 + pad, 0)
            iy1 = max(cy1 + pad, 0)
            ix2 = max(ix1 + 1, cx2 - pad)
            iy2 = max(iy1 + 1, cy2 - pad)
            cell_gray = gray[iy1:iy2, ix1:ix2]
            ch, conf = _ocr_cell_char(cell_gray)
            ch = (ch or "").strip()
            if len(ch) > 1:
                # sometimes returns multiple; keep first alnum
                for c in ch:
                    if c.isalnum():
                        ch = c
                        break
                else:
                    ch = ch[:1]

            chars.append(ch)
            # map bbox back to page coords
            wx1 = x1 + cx1
            wy1 = y1 + cy1
            wx2 = x1 + cx2
            wy2 = y1 + cy2
            w = {
                "text": ch,
                "confidence": conf,
                "bbox": [int(wx1), int(wy1), int(wx2), int(wy2)],
                "page_number": page_number,
            }
            line_words.append(w)
            all_words.append(w)

        # join chars; collapse empties
        text = "".join([c for c in chars if c])
        if text.strip():
            line_texts.append(text)
        out_lines.append({"text": text, "words": line_words})

    final_text = "\n".join([t for t in line_texts if t]).strip()

    return BoxOCRResult(
        text=final_text,
        lines=out_lines,
        words=all_words,
        debug={
            "boxed_grid_score": score,
            "box_count": len(boxes),
            "row_count": len(rows),
            **dbg_grid,
        },
    )
