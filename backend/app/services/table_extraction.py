from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import math


@dataclass
class _Word:
    text: str
    x1: int
    y1: int
    x2: int
    y2: int
    conf: Optional[float]


def _iter_words_from_block(block: Dict[str, Any]) -> List[_Word]:
    words: List[_Word] = []
    for ln in (block.get("lines") or []):
        for w in (ln.get("words") or []):
            bbox = w.get("bbox") or w.get("box") or None
            if not bbox or len(bbox) != 4:
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            txt = (w.get("text") or "").strip()
            if not txt:
                continue
            conf = w.get("confidence")
            try:
                conf_f = float(conf) if conf is not None else None
            except Exception:
                conf_f = None
            words.append(_Word(txt, x1, y1, x2, y2, conf_f))
    return words


def _median(nums: List[float]) -> float:
    if not nums:
        return 0.0
    s = sorted(nums)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return float((s[mid - 1] + s[mid]) / 2.0)


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


def _rows_from_words(words: List[_Word]) -> Tuple[List[float], float]:
    # cluster by y-center
    y_centers = [(w.y1 + w.y2) / 2.0 for w in words]
    heights = [max(1.0, (w.y2 - w.y1)) for w in words]
    med_h = max(6.0, _median(heights))
    tol = med_h * 0.6
    clusters = _cluster_1d(y_centers, tol)
    row_centers = [sum(c) / len(c) for c in clusters]
    return row_centers, tol


def _cols_from_words(words: List[_Word]) -> Tuple[List[float], float]:
    # cluster by x-center
    x_centers = [(w.x1 + w.x2) / 2.0 for w in words]
    widths = [max(1.0, (w.x2 - w.x1)) for w in words]
    med_w = max(10.0, _median(widths))
    # For UI/CSS tables, column gaps can be larger than word widths.
    # Use a blended tolerance that also scales with overall block width.
    block_x1 = min(w.x1 for w in words)
    block_x2 = max(w.x2 for w in words)
    bw = max(200.0, float(block_x2 - block_x1))
    tol = max(med_w * 0.8, bw * 0.02)
    clusters = _cluster_1d(x_centers, tol)
    col_centers = [sum(c) / len(c) for c in clusters]
    return col_centers, tol


def _nearest_index(centers: List[float], value: float) -> int:
    best_i = 0
    best_d = float("inf")
    for i, c in enumerate(centers):
        d = abs(value - c)
        if d < best_d:
            best_d = d
            best_i = i
    return best_i


def _bbox_union(bboxes: List[Tuple[int, int, int, int]]) -> Optional[List[int]]:
    if not bboxes:
        return None
    x1 = min(b[0] for b in bboxes)
    y1 = min(b[1] for b in bboxes)
    x2 = max(b[2] for b in bboxes)
    y2 = max(b[3] for b in bboxes)
    return [int(x1), int(y1), int(x2), int(y2)]


def _score_grid(n_rows: int, n_cols: int, filled_cells: int) -> float:
    total = max(1, n_rows * n_cols)
    fill_ratio = filled_cells / total
    size_bonus = min(1.0, (n_rows * n_cols) / 12.0)  # prefer non-trivial tables
    return round(0.55 * fill_ratio + 0.45 * size_bonus, 4)


def extract_tables_from_blocks(
    blocks: List[Dict[str, Any]],
    page_number: int = 0,
    *,
    enable: bool = True,
    allow_soft_fallback: bool = False,
    min_rows: int = 2,
    min_cols: int = 2,
    max_cols: int = 12,
) -> List[Dict[str, Any]]:
    """
    True table extraction (heuristic) from normalized blocks.

    Non-destructive:
    - Uses existing word bboxes
    - Returns extracted tables in a separate list (does not mutate block text)

    Strategy (fast CPU):
    - Consider only blocks tagged as `table_candidate` or type == `table_region`
    - Cluster words into row centers (by y-center) and column centers (by x-center)
    - Assign each word to nearest (row, col)
    - Build cell texts by reading order

    Output schema matches NormTable / NormTableCell in DocumentModel.
    """
    if not enable:
        return []

    tables: List[Dict[str, Any]] = []

    # IMPORTANT (production safety): By default we extract ONLY from explicit
    # table candidates/regions. The "soft fallback" path is a major source of
    # false positives (paragraphs detected as tables). Enable it only for
    # offline debugging.
    for bi, b in enumerate(blocks):
        btype = (b.get("type") or "").lower()
        is_candidate = bool(b.get("table_candidate")) or btype == "table_region"
        if not is_candidate:
            if not allow_soft_fallback:
                continue
            # soft fallback: attempt extraction from paragraph/unknown blocks with enough lines
            if btype not in {"paragraph", "unknown"}:
                continue

        words = _iter_words_from_block(b)
        if len(words) < 6:
            continue

        row_centers, _ = _rows_from_words(words)
        col_centers, _ = _cols_from_words(words)

        # prune extreme number of columns (often noise from scattered text)
        if len(col_centers) > max_cols:
            # keep the densest columns by counting assignments
            counts = [0] * len(col_centers)
            for w in words:
                xc = (w.x1 + w.x2) / 2.0
                counts[_nearest_index(col_centers, xc)] += 1
            keep = sorted(range(len(col_centers)), key=lambda i: counts[i], reverse=True)[:max_cols]
            keep = sorted(keep, key=lambda i: col_centers[i])
            col_centers = [col_centers[i] for i in keep]

        n_rows = len(row_centers)
        n_cols = len(col_centers)

        if n_rows < min_rows or n_cols < min_cols:
            continue

        # Extra sanity: ensure we have a reasonable number of lines (rows)
        # and that columns are not created from random scattered text.
        # For UI tables: columns should have support across multiple rows.
        col_support = [0] * n_cols
        for w in words:
            xc = (w.x1 + w.x2) / 2.0
            col_support[_nearest_index(col_centers, xc)] += 1
        strong_cols = sum(1 for s in col_support if s >= max(3, int(n_rows * 0.8)))
        if strong_cols < min_cols:
            continue

        # map (r,c) -> list of words
        grid: Dict[Tuple[int, int], List[_Word]] = {}
        for w in words:
            yc = (w.y1 + w.y2) / 2.0
            xc = (w.x1 + w.x2) / 2.0
            r = _nearest_index(row_centers, yc)
            c = _nearest_index(col_centers, xc)
            grid.setdefault((r, c), []).append(w)

        # Header detection (best-effort)
        header_rows: List[int] = []
        if n_rows >= 2:
            # Heuristic: first row more alpha-heavy, shorter tokens, fewer digits
            row0_words = [w for (r, _c), ws in grid.items() if r == 0 for w in ws]
            row1_words = [w for (r, _c), ws in grid.items() if r == 1 for w in ws]

            def row_stats(ws: List[_Word]) -> Tuple[int, int, float]:
                alpha = 0
                digit = 0
                lens: List[int] = []
                for ww in ws:
                    t = ww.text
                    alpha += sum(ch.isalpha() for ch in t)
                    digit += sum(ch.isdigit() for ch in t)
                    if t:
                        lens.append(len(t))
                avg_len = (sum(lens) / len(lens)) if lens else 0.0
                return alpha, digit, avg_len

            a0, d0, l0 = row_stats(row0_words)
            a1, d1, l1 = row_stats(row1_words)
            if a0 > d0 and (d0 <= d1) and (l0 <= max(22.0, l1)):
                header_rows = [0]

        # Build a dense grid for span inference
        rowcol_text = [["" for _ in range(n_cols)] for _ in range(n_rows)]
        rowcol_words: List[List[List[_Word]]] = [[[] for _ in range(n_cols)] for _ in range(n_rows)]
        for (r, c), ws in grid.items():
            if 0 <= r < n_rows and 0 <= c < n_cols:
                ws_sorted = sorted(ws, key=lambda w: (w.x1, w.y1))
                rowcol_words[r][c] = ws_sorted
                rowcol_text[r][c] = " ".join(w.text for w in ws_sorted).strip()

        cells: List[Dict[str, Any]] = []
        filled = 0
        all_word_boxes: List[Tuple[int, int, int, int]] = []

        # Span inference (best-effort):
        # - colspan: if a cell has text and next columns are empty within same row, treat as colspan
        # - rowspan: if a cell has text and below rows are empty within same column, treat as rowspan
        visited = [[False for _ in range(n_cols)] for _ in range(n_rows)]

        for r in range(n_rows):
            for c in range(n_cols):
                if visited[r][c]:
                    continue
                text = rowcol_text[r][c].strip()
                if not text:
                    continue

                # compute colspan
                colspan = 1
                cc = c + 1
                while cc < n_cols and not rowcol_text[r][cc].strip():
                    colspan += 1
                    cc += 1

                # compute rowspan
                rowspan = 1
                rr = r + 1
                while rr < n_rows and not rowcol_text[rr][c].strip():
                    rowspan += 1
                    rr += 1

                # mark visited
                for rr2 in range(r, min(n_rows, r + rowspan)):
                    for cc2 in range(c, min(n_cols, c + colspan)):
                        visited[rr2][cc2] = True

                ws_sorted = rowcol_words[r][c]
                bboxes = [(w.x1, w.y1, w.x2, w.y2) for w in ws_sorted]
                all_word_boxes.extend(bboxes)
                bbox = _bbox_union(bboxes)
                confs = [w.conf for w in ws_sorted if w.conf is not None and not math.isnan(w.conf)]
                conf = round(sum(confs) / len(confs), 4) if confs else None

                filled += 1
                cells.append(
                    {
                        "row": int(r),
                        "col": int(c),
                        "text": text,
                        "bbox": bbox,
                        "confidence": conf,
                        "rowspan": int(rowspan),
                        "colspan": int(colspan),
                        "is_header": bool(r in header_rows),
                    }
                )

        if filled < (min_rows * min_cols) - 1:
            # too sparse to be a real table
            continue

        table_bbox = _bbox_union(all_word_boxes)
        score = _score_grid(n_rows, n_cols, filled)

        tables.append(
            {
                "page_number": int(page_number),
                "source_block_index": int(bi),
                "bbox": table_bbox,
                "n_rows": int(n_rows),
                "n_cols": int(n_cols),
                "cells": cells,
                "header_rows": header_rows,
                "method": "bbox_grid_heuristic_v1",
                "score": score,
            }
        )

    return tables
