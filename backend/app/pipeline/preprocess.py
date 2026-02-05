from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings


@dataclass
class PreprocessResult:
    image: Image.Image
    blur_var: float
    contrast: float
    edge_density: float


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _save_debug(img: Image.Image, *, request_id: Optional[str], page_number: int, name: str) -> None:
    if not settings.SAVE_DEBUG_ARTIFACTS:
        return
    if not request_id:
        return
    out_dir = os.path.join(settings.ARTIFACTS_DIR, request_id)
    _ensure_dir(out_dir)
    fp = os.path.join(out_dir, f"page_{page_number:03d}_{name}.png")
    try:
        img.save(fp)
    except Exception:
        pass


def _compute_metrics(gray: np.ndarray) -> Tuple[float, float, float]:
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    blur_var = float(lap.var())
    contrast = float(gray.std())
    edges = cv2.Canny(gray, 100, 200)
    edge_density = float((edges > 0).mean())
    return blur_var, contrast, edge_density


def _deskew(gray: np.ndarray) -> np.ndarray:
    coords = np.column_stack(np.where(gray < 200))
    if coords.size == 0:
        return gray

    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    if abs(angle) < 0.5:
        return gray

    (h, w) = gray.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def preprocess_image(
    img: Image.Image,
    *,
    request_id: Optional[str] = None,
    page_number: int = 1,
    enable: Optional[bool] = None,
) -> PreprocessResult:
    if enable is None:
        enable = settings.PREPROCESS_ENABLE

    _save_debug(img, request_id=request_id, page_number=page_number, name="original")

    rgb = np.array(img.convert("RGB"))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    if not enable:
        blur_var, contrast, edge_density = _compute_metrics(gray)
        out = Image.fromarray(gray)
        _save_debug(out, request_id=request_id, page_number=page_number, name="gray")
        return PreprocessResult(image=out, blur_var=blur_var, contrast=contrast, edge_density=edge_density)

    # Resize small inputs up
    h, w = gray.shape[:2]
    min_side = min(h, w)
    target = int(settings.PREPROCESS_RESIZE_MIN_SIDE)
    if 0 < min_side < target:
        scale = target / float(min_side)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    if settings.PREPROCESS_DENOISE:
        gray = cv2.fastNlMeansDenoising(gray, None, 20, 7, 21)

    if settings.PREPROCESS_THRESHOLD:
        gray = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            35,
            11,
        )

    if settings.PREPROCESS_DESKEW:
        gray = _deskew(gray)

    blur_var, contrast, edge_density = _compute_metrics(gray)
    out = Image.fromarray(gray)
    _save_debug(out, request_id=request_id, page_number=page_number, name="preprocessed")
    return PreprocessResult(image=out, blur_var=blur_var, contrast=contrast, edge_density=edge_density)
