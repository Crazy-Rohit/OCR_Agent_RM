from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np
from PIL import Image, ImageFilter


# -----------------------------
# Script / mixed-script scoring
# -----------------------------

def _char_script(ch: str) -> str:
    """Very small, fast Unicode-range based script hinting."""
    o = ord(ch)
    # Basic Latin + Latin-1 + Latin Extended
    if (0x0041 <= o <= 0x007A) or (0x00C0 <= o <= 0x024F):
        return "latin"
    # Devanagari
    if 0x0900 <= o <= 0x097F:
        return "devanagari"
    # Arabic
    if 0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F or 0x08A0 <= o <= 0x08FF:
        return "arabic"
    # Cyrillic
    if 0x0400 <= o <= 0x04FF or 0x0500 <= o <= 0x052F:
        return "cyrillic"
    # CJK (very broad)
    if 0x4E00 <= o <= 0x9FFF or 0x3040 <= o <= 0x30FF or 0xAC00 <= o <= 0xD7AF:
        return "cjk"
    # Digits
    if ch.isdigit():
        return "digit"
    return "other"


def script_profile(text: str) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    total = 0
    for ch in (text or ""):
        if ch.isspace():
            continue
        total += 1
        s = _char_script(ch)
        counts[s] = counts.get(s, 0) + 1

    if total == 0:
        return {"total": 0, "counts": {}, "proportions": {}, "top_scripts": [], "mixed_script": False}

    props = {k: v / total for k, v in counts.items()}
    top = sorted(props.items(), key=lambda kv: kv[1], reverse=True)
    top_scripts = [{"script": k, "share": round(v, 4)} for k, v in top if k not in {"digit"}]

    meaningful = [(k, v) for (k, v) in top if k not in {"digit", "other"}]
    mixed = False
    if len(meaningful) >= 2:
        mixed = (meaningful[0][1] >= 0.30) and (meaningful[1][1] >= 0.15)

    return {
        "total": total,
        "counts": counts,
        "proportions": {k: round(v, 4) for k, v in props.items()},
        "top_scripts": top_scripts[:3],
        "mixed_script": mixed,
    }


# -----------------------------
# Noise scoring (0..1)
# -----------------------------

def _to_gray_np(img: Image.Image, max_side: int = 900) -> np.ndarray:
    im = img.convert("L")
    w, h = im.size
    s = max(w, h)
    if s > max_side:
        scale = max_side / float(s)
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)
    return np.array(im, dtype=np.float32)


def noise_score(img: Image.Image) -> float:
    """
    Heuristic noise score in [0,1]. Higher => more noisy / artifact-heavy.
    Uses edge energy + salt/pepper proxy.
    """
    g = _to_gray_np(img)
    if g.size == 0:
        return 0.0

    edges = Image.fromarray(g.astype(np.uint8)).filter(ImageFilter.FIND_EDGES)
    e = np.array(edges, dtype=np.float32) / 255.0
    edge_energy = float(np.clip(e.mean() * 2.2, 0.0, 1.0))

    p = g / 255.0
    extremes = float(((p < 0.05) | (p > 0.95)).mean())
    extremes = float(np.clip(extremes * 1.6, 0.0, 1.0))

    score = 0.6 * edge_energy + 0.4 * extremes
    return float(round(float(np.clip(score, 0.0, 1.0)), 4))


# -----------------------------
# Skew detection (degrees)
# -----------------------------

def _projection_score(bw: np.ndarray) -> float:
    proj = bw.sum(axis=1)
    if proj.size < 2:
        return 0.0
    diff = np.diff(proj)
    return float(np.var(diff))


def estimate_skew_deg(img: Image.Image, max_abs_deg: float = 5.0, step: float = 0.5) -> float:
    """
    Estimate skew angle in degrees (positive => clockwise).
    CPU-only, no OpenCV. Works best on text-heavy pages.
    """
    g = _to_gray_np(img, max_side=800)
    if g.size == 0:
        return 0.0

    thr = float(g.mean())
    bw = (g < thr).astype(np.uint8)  # text=1

    ink = float(bw.mean())
    if ink < 0.005:
        return 0.0

    pil_bw = Image.fromarray((bw * 255).astype(np.uint8))
    best_angle = 0.0
    best_score = -1.0

    a = -max_abs_deg
    while a <= max_abs_deg + 1e-9:
        rot = pil_bw.rotate(a, resample=Image.BILINEAR, expand=False, fillcolor=255)
        arr = (np.array(rot, dtype=np.uint8) < 128).astype(np.uint8)
        sc = _projection_score(arr)
        if sc > best_score:
            best_score = sc
            best_angle = a
        a += step

    if abs(best_angle) < 0.3:
        return 0.0
    return float(round(best_angle, 2))


# -----------------------------
# Document-level diagnostics v2
# -----------------------------

def compute_document_diagnostics_v2(
    *,
    page_images: List[Optional[Image.Image]],
    page_texts: List[str],
) -> Dict[str, Any]:
    """
    Non-destructive diagnostics for QA + routing explainability.

    Returns:
      {
        "v": 2,
        "pages": [{page_number, noise_score, skew_deg, script_profile, flags}],
        "summary": {...}
      }
    """
    pages_out: List[Dict[str, Any]] = []

    skew_vals: List[float] = []
    noise_vals: List[float] = []
    mixed_pages: List[int] = []

    for idx, text in enumerate(page_texts or []):
        pn = idx + 1
        img = page_images[idx] if idx < len(page_images) else None

        sp = script_profile(text or "")
        mixed = bool(sp.get("mixed_script"))
        if mixed:
            mixed_pages.append(pn)

        ns = None
        sk = None
        flags: List[str] = []

        if img is not None:
            try:
                ns = noise_score(img)
                noise_vals.append(float(ns))
                if ns >= 0.65:
                    flags.append("noisy")
            except Exception:
                ns = None

            try:
                sk = estimate_skew_deg(img)
                skew_vals.append(float(sk))
                if abs(float(sk)) >= 2.0:
                    flags.append("skewed")
            except Exception:
                sk = None

        if mixed:
            flags.append("mixed_script")

        pages_out.append(
            {
                "page_number": pn,
                "noise_score": ns,
                "skew_deg": sk,
                "script_profile": {
                    "top_scripts": sp.get("top_scripts") or [],
                    "proportions": sp.get("proportions") or {},
                    "mixed_script": mixed,
                },
                "flags": flags,
            }
        )

    avg_noise = round(float(sum(noise_vals) / len(noise_vals)), 4) if noise_vals else None
    avg_abs_skew = round(float(sum(abs(x) for x in skew_vals) / len(skew_vals)), 4) if skew_vals else None
    max_abs_skew = round(float(max(abs(x) for x in skew_vals)), 2) if skew_vals else None

    summary = {
        "avg_noise_score": avg_noise,
        "avg_abs_skew_deg": avg_abs_skew,
        "max_abs_skew_deg": max_abs_skew,
        "mixed_script_pages": mixed_pages,
        "num_pages": len(page_texts or []),
    }

    return {"v": 2, "pages": pages_out, "summary": summary}
