from __future__ import annotations

from typing import Any, Dict, List


def _cluster_1d(points: List[float], tol: float) -> List[List[float]]:
    if not points:
        return []
    pts = sorted(points)
    clusters: List[List[float]] = [[pts[0]]]
    for p in pts[1:]:
        if abs(p - clusters[-1][-1]) <= tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return clusters


def _median(nums: List[float]) -> float:
    if not nums:
        return 0.0
    s = sorted(nums)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return float((s[mid - 1] + s[mid]) / 2.0)


def _looks_like_table_by_alignment(block: Dict[str, Any]) -> bool:
    """Detect borderless/CSS tables using word bbox alignment."""
    lines = block.get("lines") or []
    if len(lines) < 3:
        return False

    sample_lines = lines[: min(10, len(lines))]
    x_centers: List[float] = []
    widths: List[float] = []
    non_empty = 0

    for ln in sample_lines:
        ws = ln.get("words") or []
        if len(ws) < 3:
            continue
        non_empty += 1
        for w in ws:
            bbox = w.get("bbox") or w.get("box")
            if not bbox or len(bbox) != 4:
                continue
            try:
                x1, y1, x2, y2 = [float(v) for v in bbox]
            except Exception:
                continue
            x_centers.append((x1 + x2) / 2.0)
            widths.append(max(1.0, x2 - x1))

    if non_empty < 3 or len(x_centers) < 15:
        return False

    # scale tolerance by block width for CSS spacing
    bb = block.get("bbox")
    if isinstance(bb, dict):
        bw = float(abs((bb.get("x2", 0) or 0) - (bb.get("x1", 0) or 0))) or 1000.0
    elif isinstance(bb, list) and len(bb) == 4:
        bw = float(abs(bb[2] - bb[0])) or 1000.0
    else:
        bw = 1000.0

    tol = max(_median(widths) * 0.9, bw * 0.02)
    clusters = _cluster_1d(x_centers, tol)

    # keep clusters that appear across many lines
    support = [len(c) for c in clusters]
    strong_cols = [s for s in support if s >= max(3, non_empty)]
    return len(strong_cols) >= 3


def mark_table_candidates(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Tag blocks as table candidates.

    v2 improvements:
    - Old text-gap heuristic kept
    - New bbox-alignment heuristic added (captures UI/CSS tables)
    """
    out: List[Dict[str, Any]] = []
    for b in blocks or []:
        text = (b.get("text") or "")
        lines = text.splitlines()

        multi_space_lines = sum(1 for ln in lines if "  " in ln)
        numeric_tokens = sum(1 for tok in text.replace("\n", " ").split() if tok.strip(".,()").isdigit())
        strong_text = bool(lines) and (multi_space_lines >= max(2, int(0.5 * len(lines)))) and (numeric_tokens >= 6)

        strong_bbox = _looks_like_table_by_alignment(b)

        b2 = dict(b)
        if strong_text or strong_bbox:
            b2["table_candidate"] = True
            b2["type"] = "table_region"
            b2.setdefault("table_candidate_reason", "bbox_alignment" if strong_bbox else "text_gaps")
        else:
            b2["table_candidate"] = False
        out.append(b2)
    return out
