import cv2
import numpy as np
import pytesseract
from typing import List, Dict, Any


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
