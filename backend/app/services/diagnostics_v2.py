from __future__ import annotations

from typing import Any, Dict, Tuple
import math
import numpy as np
import cv2
from PIL import Image


def _pil_to_gray(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("L"))


def estimate_noise_score(page_image: Image.Image) -> float:
    """
    Rough noise score in [0,1]. Higher means noisier.
    Uses edge density + small connected components heuristic.
    """
    gray = _pil_to_gray(page_image)
    # downscale for speed
    h,w = gray.shape[:2]
    scale = 900 / max(h,w) if max(h,w) > 900 else 1.0
    if scale != 1.0:
        gray = cv2.resize(gray, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)

    blur = cv2.GaussianBlur(gray, (3,3), 0)
    edges = cv2.Canny(blur, 50, 150)
    edge_density = float(np.count_nonzero(edges)) / float(edges.size + 1e-6)

    # small components in binarized image
    bin_inv = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY_INV, 35, 10)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(bin_inv, connectivity=8)
    # count small blobs (exclude background=0)
    small = 0
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if 5 <= area <= 40:
            small += 1
    small_density = small / float(gray.size / 10000.0 + 1e-6)  # per 10k px

    # combine
    score = 0.6*min(1.0, edge_density*8.0) + 0.4*min(1.0, small_density/50.0)
    return float(max(0.0, min(1.0, score)))


def estimate_skew_deg(page_image: Image.Image) -> float:
    """
    Estimate skew angle in degrees. Positive means clockwise.
    Uses minimum area rectangle over text pixels.
    """
    gray = _pil_to_gray(page_image)
    # binarize
    bin_inv = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                   cv2.THRESH_BINARY_INV, 35, 10)
    coords = np.column_stack(np.where(bin_inv > 0))
    if coords.shape[0] < 200:
        return 0.0
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    # OpenCV angle conventions
    if angle < -45:
        angle = 90 + angle
    # convert to clockwise-positive
    skew = -float(angle)
    if abs(skew) > 45:
        skew = 0.0
    return skew


def script_profile(text: str) -> Dict[str, float]:
    """
    Very lightweight script ratio estimation from Unicode ranges.
    Returns proportions for latin, digit, devanagari, arabic, other.
    """
    counts = {"latin":0, "digit":0, "devanagari":0, "arabic":0, "other":0}
    total = 0
    for ch in text or "":
        if ch.isspace():
            continue
        total += 1
        o = ord(ch)
        if 48 <= o <= 57:
            counts["digit"] += 1
        elif (65 <= o <= 90) or (97 <= o <= 122) or (0x00C0 <= o <= 0x024F):
            counts["latin"] += 1
        elif 0x0900 <= o <= 0x097F:
            counts["devanagari"] += 1
        elif 0x0600 <= o <= 0x06FF:
            counts["arabic"] += 1
        else:
            counts["other"] += 1
    if total == 0:
        return {k:0.0 for k in counts}
    return {k: float(v)/float(total) for k,v in counts.items()}


def compute_page_diagnostics(page_image: Image.Image, page_text: str) -> Dict[str, Any]:
    noise = estimate_noise_score(page_image)
    skew = estimate_skew_deg(page_image)
    sp = script_profile(page_text)

    mixed = sum(1 for k,v in sp.items() if k not in ("other",) and v >= 0.15) >= 2
    return {
        "noise_score": float(noise),
        "skew_deg": float(skew),
        "script_profile": sp,
        "flags": {
            "noisy": bool(noise >= 0.55),
            "skewed": bool(abs(skew) >= 2.5),
            "mixed_script": bool(mixed),
        }
    }
