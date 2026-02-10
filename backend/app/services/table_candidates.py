from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _bbox_x1x2(bbox: Any) -> Optional[Tuple[int, int]]:
    """Normalize bbox into (x1, x2).

    Supports:
      - dict: {"x1":..,"y1":..,"x2":..,"y2":..}
      - list/tuple: [x1,y1,x2,y2]
    Returns None if bbox is unusable.
    """
    try:
        if isinstance(bbox, dict):
            if "x1" in bbox and "x2" in bbox:
                return int(bbox["x1"]), int(bbox["x2"])
            return None
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            return int(bbox[0]), int(bbox[2])
    except Exception:
        return None
    return None


def mark_table_candidates(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Conservative table detection.

    Fixes crash when word bbox is stored as a list instead of dict.
    Avoids false positives on bullets/lists and boxed-form grids.
    """
    for b in blocks:
        b["table_candidate"] = False

        # Never treat boxed form-field regions as tables
        if b.get("form_box_region"):
            continue

        btype = (b.get("type") or "").strip()
        text = (b.get("text") or "").strip()

        # Lists/headings are not tables
        if btype in {"list_item", "heading"}:
            continue

        # Avoid bullet paragraphs becoming tables
        first_line = text.splitlines()[0].strip() if text else ""
        if first_line.startswith(("•", "-", "*")) or first_line[:2].lower() in {"e ", "o "}:
            continue

        # Too short to be a table region
        if len(text) < 80:
            continue

        lines = b.get("lines") or []
        if len(lines) < 3:
            continue

        # Collect x-centers
        x_centers: List[int] = []
        for ln in lines:
            for w in (ln.get("words") or []):
                x1x2 = _bbox_x1x2(w.get("bbox"))
                if not x1x2:
                    continue
                x1, x2 = x1x2
                if x2 <= x1:
                    continue
                x_centers.append((x1 + x2) // 2)

        if len(x_centers) < 18:
            continue

        x_centers.sort()

        # Cluster x-centers into columns
        clusters: List[List[int]] = []
        tol = 18
        for x in x_centers:
            if not clusters or abs(x - clusters[-1][-1]) > tol:
                clusters.append([x])
            else:
                clusters[-1].append(x)

        meaningful = [c for c in clusters if len(c) >= 3]

        # Require at least 3 stable columns
        if len(meaningful) >= 3:
            b["table_candidate"] = True

    return blocks
