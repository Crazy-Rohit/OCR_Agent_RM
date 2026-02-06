from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional


def classify_page(words: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    """
    Heuristic routing hook (safe + non-breaking).
    We do NOT attempt true handwriting OCR here; we only tag likely cases.

    Signals:
    - avg confidence low
    - many very short tokens
    - sparse text
    """
    toks = [(w.get("text") or "").strip() for w in (words or [])]
    toks = [t for t in toks if t]
    n = len(toks)

    confs = []
    for w in (words or []):
        c = w.get("confidence")
        if isinstance(c, (int, float)):
            if 0.0 <= float(c) <= 1.0:
                confs.append(float(c))
    avg_conf = (sum(confs) / len(confs)) if confs else None

    short_ratio = (sum(1 for t in toks if len(t) <= 2) / n) if n else 1.0

    # Conservative classification
    classification = "unknown"
    if n == 0:
        classification = "unknown"
    elif avg_conf is not None and avg_conf >= 0.65:
        classification = "printed"
    elif avg_conf is not None and avg_conf <= 0.35 and short_ratio >= 0.55:
        classification = "mixed"  # could be handwriting or noisy scan
    else:
        classification = "unknown"

    return classification, {
        "word_count": n,
        "avg_conf": avg_conf,
        "short_token_ratio": short_ratio,
    }
