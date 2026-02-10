from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _word_height(word: Dict[str, Any]) -> Optional[float]:
    bbox = word.get("bbox")
    if not (isinstance(bbox, list) and len(bbox) == 4):
        return None
    try:
        y1 = float(bbox[1])
        y2 = float(bbox[3])
        h = max(0.0, y2 - y1)
        return h if h > 0 else None
    except Exception:
        return None


def _norm_conf(c: Any) -> Optional[float]:
    """Normalize confidence to 0..1 if it looks like 0..100."""
    if not isinstance(c, (int, float)):
        return None
    v = float(c)
    if v < 0:
        return None
    if v > 1.0:
        # assume 0..100
        v = min(100.0, v) / 100.0
    return max(0.0, min(1.0, v))


def detect_handwriting_block(block: Dict[str, Any]) -> Tuple[str, float, Dict[str, Any]]:
    """
    Cheap, non-destructive handwriting detector.

    Returns:
      (script, score, signals)

    script: "printed" | "handwritten" | "unknown"
    score:  0..1 likelihood of handwriting

    Notes:
    - This is NOT handwriting OCR.
    - This is conservative: we only mark handwritten when multiple signals agree.
    """

    words: List[Dict[str, Any]] = []
    for ln in (block.get("lines") or []):
        for w in (ln.get("words") or []):
            if isinstance(w, dict) and (w.get("text") or "").strip():
                words.append(w)

    n_words = len(words)
    if n_words == 0:
        # Cursive/noisy handwriting often yields no tokens from Tesseract.
        # Do NOT hard-fail to 0; provide a weak signal so orchestrator can try TrOCR fallback.
        return "unknown", 0.25, {"reason": "no_words", "word_count": 0, "trocr_fallback_hint": True}

    if n_words < 5:
        confs = []
        for w in words:
            nc = _norm_conf(w.get("confidence"))
            if nc is not None:
                confs.append(nc)
        avg_conf = (sum(confs) / len(confs)) if confs else None

        toks = [(w.get("text") or "").strip() for w in words]
        short_ratio = sum(1 for t in toks if len(t) <= 2) / n_words

        score = 0.0
        if avg_conf is not None:
            if avg_conf <= 0.45:
                score += 0.45
            elif avg_conf <= 0.55:
                score += 0.25
        if short_ratio >= 0.60:
            score += 0.25

        score = max(0.15, min(0.65, score))
        return "unknown", score, {
            "reason": "few_words",
            "word_count": n_words,
            "avg_conf": avg_conf,
            "short_token_ratio": short_ratio,
            "trocr_fallback_hint": True,
        }

    # confidences
    confs = []
    for w in words:
        nc = _norm_conf(w.get("confidence"))
        if nc is not None:
            confs.append(nc)
    avg_conf = (sum(confs) / len(confs)) if confs else None

    # token statistics
    toks = [(w.get("text") or "").strip() for w in words]
    short_ratio = sum(1 for t in toks if len(t) <= 2) / n_words
    digit_ratio = sum(1 for t in toks if t.isdigit()) / n_words

    # bbox / height statistics
    heights = []
    for w in words:
        h = _word_height(w)
        if h is not None:
            heights.append(h)
    mean_h = (sum(heights) / len(heights)) if heights else None
    if heights and mean_h and mean_h > 0:
        var_h = sum((h - mean_h) ** 2 for h in heights) / len(heights)
        std_h = var_h ** 0.5
        height_cv = std_h / mean_h
    else:
        height_cv = None

    # Signals (0..1 each)
    s_low_conf = 0.0
    if avg_conf is not None:
        # low average confidence is common for handwriting/noisy scans
        # thresholds are conservative
        if avg_conf <= 0.45:
            s_low_conf = 1.0
        elif avg_conf <= 0.55:
            s_low_conf = 0.5

    s_height_var = 0.0
    if height_cv is not None:
        # handwriting tends to have higher variability in word heights
        if height_cv >= 0.45:
            s_height_var = 1.0
        elif height_cv >= 0.30:
            s_height_var = 0.6

    s_token_noise = 0.0
    # too many tiny tokens often indicates shaky recognition
    if short_ratio >= 0.60:
        s_token_noise = 1.0
    elif short_ratio >= 0.45:
        s_token_noise = 0.5

    # digits-heavy blocks are often printed tables/forms; reduce handwriting likelihood
    s_digit_penalty = 0.0
    if digit_ratio >= 0.55:
        s_digit_penalty = 0.6

    # Weighted score
    score = (0.45 * s_low_conf) + (0.40 * s_height_var) + (0.25 * s_token_noise) - (0.30 * s_digit_penalty)
    score = max(0.0, min(1.0, score))

    # Script decision (conservative)
    if score >= 0.70 and (s_low_conf > 0 or s_height_var > 0):
        script = "handwritten"
    elif avg_conf is not None and avg_conf >= 0.70 and (height_cv is None or height_cv < 0.25):
        script = "printed"
    else:
        script = "unknown"

    return script, score, {
        "word_count": n_words,
        "avg_conf": avg_conf,
        "short_token_ratio": short_ratio,
        "digit_ratio": digit_ratio,
        "height_cv": height_cv,
        "signals": {
            "low_conf": s_low_conf,
            "height_variance": s_height_var,
            "token_noise": s_token_noise,
            "digit_penalty": s_digit_penalty,
        },
    }


def aggregate_page_script(block_scripts: List[str]) -> Tuple[str, Dict[str, Any]]:
    """Aggregate block scripts into a page label."""
    total = len(block_scripts)
    if total == 0:
        return "unknown", {"handwritten_ratio": 0.0, "printed_ratio": 0.0, "unknown_ratio": 1.0}

    hw = sum(1 for s in block_scripts if s == "handwritten")
    pr = sum(1 for s in block_scripts if s == "printed")
    un = total - hw - pr

    hw_r = hw / total
    pr_r = pr / total
    un_r = un / total

    if hw_r >= 0.60:
        label = "handwritten"
    elif hw_r >= 0.20:
        label = "mixed"
    elif pr_r >= 0.60:
        label = "printed"
    else:
        label = "unknown"

    return label, {"handwritten_ratio": hw_r, "printed_ratio": pr_r, "unknown_ratio": un_r, "block_count": total}
