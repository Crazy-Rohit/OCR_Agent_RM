from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class Classification:
    category: str
    confidence: float
    signals: Dict[str, float]


def classify_from_signals(*, blur_var: float, contrast: float, edge_density: float) -> Classification:
    """Lightweight heuristic classifier.

    V1: simple + fast (no ML dependency).
    """

    signals = {
        "blur_var": float(blur_var),
        "contrast": float(contrast),
        "edge_density": float(edge_density),
    }

    if edge_density > 0.09 and contrast > 55:
        return Classification(category="screenshot", confidence=0.75, signals=signals)

    if contrast < 35 or blur_var < 70:
        return Classification(category="scanned_pdf", confidence=0.7, signals=signals)

    if 35 <= contrast <= 55 and edge_density < 0.08:
        return Classification(category="handwritten_form", confidence=0.45, signals=signals)

    return Classification(category="printed_form", confidence=0.55, signals=signals)
