from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


def score_page(words: List[Dict[str, Any]], text: str) -> Dict[str, Any]:
    """Heuristic scoring only (NO filtering)."""
    confs: List[float] = []
    for w in words or []:
        c = w.get("confidence")
        cf = _safe_float(c)
        if cf is None:
            continue
        # confidence in your pipeline is 0..1
        if 0.0 <= cf <= 1.0:
            confs.append(cf)

    avg_conf = sum(confs) / len(confs) if confs else None
    word_count = len([w for w in (words or []) if (w.get("text") or "").strip()])
    char_count = len((text or "").strip())

    # simple quality score: blend avg_conf and text volume (log-ish)
    volume = min(1.0, (char_count / 800.0))  # saturate around 800 chars
    conf_component = avg_conf if avg_conf is not None else 0.0
    quality = 0.65 * conf_component + 0.35 * volume

    return {
        "avg_conf": avg_conf,
        "word_count": word_count,
        "char_count": char_count,
        "quality_score": quality,
    }
