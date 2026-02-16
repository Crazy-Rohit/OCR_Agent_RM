from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import statistics


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


def _clean_text(s: Any) -> str:
    return (s or "").strip()


def _word_bbox(w: Dict[str, Any]) -> Tuple[int, int, int, int]:
    """Support both:
    - current word format: {"bbox":[x1,y1,x2,y2]}
    - tesseract raw format: left/top/width/height
    """
    if "bbox" in w and w["bbox"]:
        bb = w["bbox"]
        if isinstance(bb, (list, tuple)) and len(bb) == 4:
            return _safe_int(bb[0]), _safe_int(bb[1]), _safe_int(bb[2]), _safe_int(bb[3])

    l = _safe_int(w.get("left"))
    t = _safe_int(w.get("top"))
    ww = _safe_int(w.get("width"))
    hh = _safe_int(w.get("height"))
    return l, t, l + ww, t + hh


def _median(values: List[float], default: float) -> float:
    values = [v for v in values if v is not None and v > 0]
    if not values:
        return default
    return float(statistics.median(values))


def _estimate_space_threshold(words: List[Dict[str, Any]]) -> float:
    char_widths: List[float] = []
    for w in words:
        txt = _clean_text(w.get("text"))
        if not txt:
            continue
        l, t, r, b = _word_bbox(w)
        w_width = max(1, r - l)
        cw = w_width / max(1, len(txt))
        if cw > 0:
            char_widths.append(cw)
    med_cw = _median(char_widths, default=7.0)
    return med_cw * 1.5


@dataclass
class Line:
    words: List[Dict[str, Any]]
    left: int
    top: int
    right: int
    bottom: int

    @property
    def height(self) -> int:
        return max(1, self.bottom - self.top)

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": line_text_from_words(self.words),
            "bbox": {"x1": self.left, "y1": self.top, "x2": self.right, "y2": self.bottom, "left": self.left, "top": self.top, "right": self.right, "bottom": self.bottom},
            "words": self.words,
        }


def line_text_from_words(words: List[Dict[str, Any]]) -> str:
    ws = sorted(words, key=lambda w: _safe_int(_word_bbox(w)[0]))
    if not ws:
        return ""
    space_thr = _estimate_space_threshold(ws)
    parts: List[str] = []
    prev_r: Optional[int] = None

    for w in ws:
        txt = _clean_text(w.get("text"))
        if not txt:
            continue
        l, t, r, b = _word_bbox(w)
        if prev_r is None:
            parts.append(txt)
        else:
            gap = l - prev_r
            if gap > space_thr:
                parts.append(txt)
            else:
                # still separate by space (keeps readability)
                parts.append(txt)
        prev_r = r

    return " ".join(" ".join(parts).split()).strip()


def build_lines(words: List[Dict[str, Any]]) -> List[Line]:
    tokens = [w for w in words if _clean_text(w.get("text"))]
    if not tokens:
        return []

    heights = []
    for w in tokens:
        l, t, r, b = _word_bbox(w)
        heights.append(max(1, b - t))
    med_h = _median([float(h) for h in heights], default=12.0)
    y_tol = max(4.0, med_h * 0.6)

    tokens.sort(key=lambda w: (_safe_int(_word_bbox(w)[1]), _safe_int(_word_bbox(w)[0])))

    lines: List[Line] = []
    for w in tokens:
        l, t, r, b = _word_bbox(w)
        cy = (t + b) / 2.0

        placed = False
        for ln in lines:
            if abs(cy - ln.center_y) <= y_tol:
                ln.words.append(w)
                ln.left = min(ln.left, l)
                ln.top = min(ln.top, t)
                ln.right = max(ln.right, r)
                ln.bottom = max(ln.bottom, b)
                placed = True
                break

        if not placed:
            lines.append(Line(words=[w], left=l, top=t, right=r, bottom=b))

    for ln in lines:
        ln.words.sort(key=lambda w: _safe_int(_word_bbox(w)[0]))
    lines.sort(key=lambda ln: (ln.top, ln.left))
    return lines


def build_blocks(lines: List[Line]) -> List[Dict[str, Any]]:
    if not lines:
        return []

    line_heights = [ln.height for ln in lines]
    med_lh = _median([float(h) for h in line_heights], default=14.0)

    gap_thr = max(8.0, med_lh * 1.3)
    indent_thr = 25.0

    blocks: List[Dict[str, Any]] = []
    cur_lines: List[Line] = []
    cur_bbox: Optional[Tuple[int, int, int, int]] = None
    cur_left_anchor: Optional[int] = None
    prev_bottom: Optional[int] = None

    def flush():
        nonlocal cur_lines, cur_bbox, cur_left_anchor, prev_bottom
        if not cur_lines or cur_bbox is None:
            cur_lines, cur_bbox, cur_left_anchor, prev_bottom = [], None, None, None
            return
        texts = [line_text_from_words(ln.words) for ln in cur_lines]
        texts = [t for t in texts if t]
        block_text = "\n".join(texts).strip()

        l, t, r, b = cur_bbox
        blocks.append({
            "text": block_text,
            "bbox": {"x1": l, "y1": t, "x2": r, "y2": b, "left": l, "top": t, "right": r, "bottom": b},
            "lines": [ln.to_dict() for ln in cur_lines],
        })

        cur_lines, cur_bbox, cur_left_anchor, prev_bottom = [], None, None, None

    for ln in lines:
        if not cur_lines:
            cur_lines = [ln]
            cur_bbox = (ln.left, ln.top, ln.right, ln.bottom)
            cur_left_anchor = ln.left
            prev_bottom = ln.bottom
            continue

        vgap = float(ln.top - (prev_bottom or ln.top))
        indent_shift = abs(float(ln.left - (cur_left_anchor or ln.left)))

        if vgap > gap_thr or indent_shift > indent_thr:
            flush()
            cur_lines = [ln]
            cur_bbox = (ln.left, ln.top, ln.right, ln.bottom)
            cur_left_anchor = ln.left
            prev_bottom = ln.bottom
            continue

        cur_lines.append(ln)
        l, t, r, b = cur_bbox
        cur_bbox = (min(l, ln.left), min(t, ln.top), max(r, ln.right), max(b, ln.bottom))
        prev_bottom = max(prev_bottom or ln.bottom, ln.bottom)

    flush()
    return blocks


def build_layout(
    words: List[Dict[str, Any]],
    *,
    page_width: Optional[int] = None,
    page_height: Optional[int] = None,
) -> Dict[str, Any]:
    lines = build_lines(words)
    blocks = build_blocks(lines)

    block_texts = [b["text"] for b in blocks if b.get("text")]
    full_text = "\n\n".join(block_texts).strip()

    return {
        "lines": [ln.to_dict() for ln in lines],
        "blocks": blocks,
        "tables": [],
        "text": full_text,
        "width": page_width,
        "height": page_height,
    }
