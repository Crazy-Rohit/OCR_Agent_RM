from __future__ import annotations

from typing import List, Tuple
from PIL import Image, ImageOps, ImageFilter

try:
    import numpy as np  # type: ignore
except Exception:
    np = None  # type: ignore

TROCR_BUILD_ID = "TROCR_V5_BASE_BINARIZE_INVERT_LINESEG"

_MODEL = None
_PROCESSOR = None
_DEVICE = None


def _lazy_load_trocr():
    """
    Load TrOCR once per process.
    Uses BASE model (~600MB) for faster downloads and stable CPU inference.
    """
    global _MODEL, _PROCESSOR, _DEVICE
    if _MODEL is not None:
        return

    import torch
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel

    model_name = "microsoft/trocr-base-handwritten"

    print(f"[{TROCR_BUILD_ID}] Using model: {model_name}")

    # Use slow processor for stable behavior across transformers versions
    _PROCESSOR = TrOCRProcessor.from_pretrained(model_name, use_fast=False)
    _MODEL = VisionEncoderDecoderModel.from_pretrained(model_name)

    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    _MODEL.to(_DEVICE)
    _MODEL.eval()


def _otsu_threshold(gray: "np.ndarray") -> int:
    """
    Deterministic Otsu threshold on uint8 image.
    """
    # histogram
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = gray.size
    if total == 0:
        return 128
    sum_total = np.dot(np.arange(256), hist)

    sum_b = 0.0
    w_b = 0.0
    max_var = -1.0
    threshold = 128

    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_total - sum_b) / w_f
        var_between = w_b * w_f * (m_b - m_f) ** 2
        if var_between > max_var:
            max_var = var_between
            threshold = t
    return int(threshold)


def _remove_ruling_lines_binary(bin_img: "np.ndarray") -> "np.ndarray":
    """
    Deterministic suppression of notebook ruling lines in a binary (0/255) image.
    Treats thin, wide horizontal strokes as lines and removes them.
    """
    # bin_img: 0 = ink, 255 = background
    ink = (bin_img == 0)
    row_ink_ratio = ink.mean(axis=1)

    # Rows with a lot of ink across width likely correspond to ruling lines.
    # Keep it deterministic.
    line_rows = row_ink_ratio > 0.18
    if not line_rows.any():
        return bin_img

    out = bin_img.copy()
    ys = np.where(line_rows)[0]
    for y in ys:
        # only remove if the row is "thin-ish" in local neighborhood
        y0 = max(0, y - 2)
        y1 = min(out.shape[0], y + 3)
        band = ink[y0:y1].mean(axis=0)
        # replace row with background unless there's substantial vertical stroke evidence nearby
        out[y] = np.where(band > 0.25, out[y], 255).astype(np.uint8)

    return out


def _preprocess(img: Image.Image) -> Image.Image:
    """
    Deterministic preprocessing:
    - Upscale aggressively (your image is small)
    - Autocontrast
    - Otsu binarization
    - Remove notebook ruling lines (binary domain)
    - Sharpen
    """
    img = img.convert("RGB")
    w, h = img.size
    if max(w, h) < 1200:
        img = img.resize((w * 3, h * 3), Image.BICUBIC)

    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray, cutoff=1)

    if np is None:
        # fallback: just sharpen and return
        gray = gray.filter(ImageFilter.UnsharpMask(radius=2, percent=180, threshold=2))
        return gray.convert("RGB")

    arr = np.array(gray, dtype=np.uint8)
    t = _otsu_threshold(arr)
    bin_img = np.where(arr > t, 255, 0).astype(np.uint8)

    bin_img = _remove_ruling_lines_binary(bin_img)

    # Convert back to PIL
    pil = Image.fromarray(bin_img, mode="L")
    pil = pil.filter(ImageFilter.UnsharpMask(radius=2, percent=200, threshold=1))
    return pil.convert("RGB")


def _segment_lines(proc_rgb: Image.Image) -> List[Tuple[int, int]]:
    """
    Deterministic line segmentation using horizontal ink projection on binarized image.
    """
    if np is None:
        return [(0, proc_rgb.size[1])]

    arr = np.array(proc_rgb.convert("L"), dtype=np.uint8)
    ink = (arr < 128).astype(np.float32)  # binarized: ink=1
    proj = ink.mean(axis=1)

    # Smooth projection
    k = 13
    pad = k // 2
    proj_pad = np.pad(proj, (pad, pad), mode="edge")
    smooth = np.convolve(proj_pad, np.ones(k) / k, mode="valid")

    thr = 0.01
    is_text = smooth > thr

    segments: List[Tuple[int, int]] = []
    y = 0
    H = len(is_text)
    while y < H:
        if not is_text[y]:
            y += 1
            continue
        y0 = y
        while y < H and is_text[y]:
            y += 1
        y1 = y

        # margins
        y0 = max(0, y0 - 22)
        y1 = min(H, y1 + 22)

        if (y1 - y0) >= 55:
            segments.append((y0, y1))

    if not segments:
        return [(0, proc_rgb.size[1])]

    # merge close segments
    merged: List[Tuple[int, int]] = []
    for y0, y1 in segments:
        if not merged:
            merged.append((y0, y1))
        else:
            py0, py1 = merged[-1]
            if y0 - py1 < 30:
                merged[-1] = (py0, max(py1, y1))
            else:
                merged.append((y0, y1))

    return merged


def _score_text(s: str) -> int:
    """
    Deterministic scoring to choose between normal vs inverted decode.
    Prefers alphabetic content and length; penalizes digits/noise.
    """
    if not s:
        return -10_000
    alpha = sum(ch.isalpha() for ch in s)
    digits = sum(ch.isdigit() for ch in s)
    spaces = s.count(" ")
    # noise characters often seen in garbage decodes
    noise = sum(ch in "|[]{}<>_~" for ch in s)
    length = len(s)
    return alpha * 6 + spaces * 2 + length - digits * 6 - noise * 10


def _decode_line(line_img: Image.Image) -> str:
    import torch

    # decode both normal + inverted and take best score
    variants = [line_img, ImageOps.invert(line_img.convert("L")).convert("RGB")]

    best = ""
    best_score = -10_000

    for v in variants:
        pixel_values = _PROCESSOR(images=v, return_tensors="pt").pixel_values.to(_DEVICE)

        with torch.no_grad():
            ids = _MODEL.generate(
                pixel_values,
                num_beams=5,
                max_new_tokens=96,
                early_stopping=True,
            )
        txt = _PROCESSOR.batch_decode(ids, skip_special_tokens=True)[0].strip()

        sc = _score_text(txt)
        if sc > best_score:
            best_score = sc
            best = txt

    return best


def trocr_ocr_crops(page_image: Image.Image, crops: List[Tuple[int, int, int, int]]) -> List[str]:
    """
    OCR each crop using TrOCR.
    For multi-line handwriting, runs deterministic line segmentation and decodes line-by-line.
    """
    _lazy_load_trocr()

    results: List[str] = []
    for (x1, y1, x2, y2) in crops:
        crop = page_image.crop((x1, y1, x2, y2))
        proc = _preprocess(crop)

        lines = _segment_lines(proc)

        out_lines: List[str] = []
        for (ly0, ly1) in lines:
            line_img = proc.crop((0, ly0, proc.size[0], ly1))
            txt = _decode_line(line_img)
            if txt:
                out_lines.append(txt)

        results.append("\n".join(out_lines).strip())

    return results
