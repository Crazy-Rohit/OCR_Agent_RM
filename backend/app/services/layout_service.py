import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple

from app.models.schemas import WordBox, LineBox, BlockBox, TableBox


# -----------------------------
# Words -> Lines
# -----------------------------

@dataclass
class _Word:
    text: str
    x1: int
    y1: int
    x2: int
    y2: int
    conf: Optional[float]

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    @property
    def h(self) -> int:
        return max(1, self.y2 - self.y1)


def words_to_lines(words: List[WordBox]) -> List[LineBox]:
    """
    Group OCR words into lines using Y-center clustering + X sorting.
    Returns lines in top-to-bottom order.
    """
    if not words:
        return []

    wds = [
        _Word(w.text, w.x1, w.y1, w.x2, w.y2, w.confidence)
        for w in words
        if (w.text or "").strip()
    ]
    if not wds:
        return []

    heights = sorted(w.h for w in wds)
    median_h = heights[len(heights) // 2]
    y_tol = max(6, int(median_h * 0.6))

    wds.sort(key=lambda w: (w.cy, w.x1))

    lines: List[List[_Word]] = []

    for w in wds:
        placed = False
        for line in reversed(lines[-8:]):  # speed: check recent lines
            line_cy = sum(x.cy for x in line) / len(line)
            if abs(w.cy - line_cy) <= y_tol:
                line.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])

    lines.sort(key=lambda line: sum(x.cy for x in line) / len(line))

    out: List[LineBox] = []
    char_w = max(4, int(median_h * 0.45))

    for line in lines:
        line.sort(key=lambda w: w.x1)

        parts: List[str] = []
        prev_x2 = None

        confs: List[float] = []
        x1 = min(w.x1 for w in line)
        y1 = min(w.y1 for w in line)
        x2 = max(w.x2 for w in line)
        y2 = max(w.y2 for w in line)

        for w in line:
            if w.conf is not None and w.conf >= 0:
                confs.append(w.conf)

            if prev_x2 is None:
                parts.append(w.text)
            else:
                gap = w.x1 - prev_x2
                if gap > char_w:
                    parts.append(" ")
                parts.append(w.text)
            prev_x2 = w.x2

        text = "".join(parts).strip()
        avg_conf = (sum(confs) / len(confs)) if confs else None

        out.append(
            LineBox(
                text=text,
                x1=int(x1),
                y1=int(y1),
                x2=int(x2),
                y2=int(y2),
                confidence=avg_conf,
            )
        )

    return out


# -----------------------------
# Lines -> Blocks (+ reading order)
# -----------------------------

def order_blocks_reading(blocks: List[BlockBox]) -> List[BlockBox]:
    """
    Basic reading order:
    - Cluster blocks into columns based on x1 proximity
    - Sort columns left-to-right
    - Sort blocks in each column top-to-bottom
    """
    if not blocks:
        return []

    bs = sorted(blocks, key=lambda b: (b.x1, b.y1))

    widths = sorted(max(1, b.x2 - b.x1) for b in bs)
    median_w = widths[len(widths) // 2]
    col_tol = max(40, int(median_w * 0.35))

    columns: List[List[BlockBox]] = []

    for b in bs:
        placed = False
        for col in columns:
            xs = sorted(x.x1 for x in col)
            anchor = xs[len(xs) // 2]
            if abs(b.x1 - anchor) <= col_tol:
                col.append(b)
                placed = True
                break
        if not placed:
            columns.append([b])

    def col_anchor(col: List[BlockBox]) -> int:
        xs = sorted(x.x1 for x in col)
        return xs[len(xs) // 2]

    columns.sort(key=col_anchor)

    for col in columns:
        col.sort(key=lambda b: (b.y1, b.x1))

    ordered: List[BlockBox] = []
    for col in columns:
        ordered.extend(col)

    return ordered


def lines_to_blocks(lines: List[LineBox]) -> List[BlockBox]:
    """
    Group lines into blocks using vertical gap + indentation similarity.
    Returns blocks in reading order.
    """
    if not lines:
        return []

    indexed = list(enumerate(lines))
    indexed.sort(key=lambda it: (it[1].y1, it[1].x1))

    heights = sorted(max(1, ln.y2 - ln.y1) for _, ln in indexed)
    median_h = heights[len(heights) // 2]
    gap_tol = max(10, int(median_h * 0.9))
    indent_tol = max(12, int(median_h * 0.8))

    blocks: List[BlockBox] = []

    cur_line_idxs: List[int] = []
    cur_lines: List[LineBox] = []

    def flush_block():
        nonlocal cur_line_idxs, cur_lines, blocks
        if not cur_lines:
            return

        x1 = min(l.x1 for l in cur_lines)
        y1 = min(l.y1 for l in cur_lines)
        x2 = max(l.x2 for l in cur_lines)
        y2 = max(l.y2 for l in cur_lines)

        text = "\n".join(l.text for l in cur_lines).strip()
        confs = [l.confidence for l in cur_lines if l.confidence is not None]
        avg_conf = (sum(confs) / len(confs)) if confs else None

        blocks.append(
            BlockBox(
                block_type="text",
                text=text,
                x1=int(x1),
                y1=int(y1),
                x2=int(x2),
                y2=int(y2),
                confidence=avg_conf,
                line_indexes=cur_line_idxs.copy(),
            )
        )
        cur_line_idxs = []
        cur_lines = []

    prev_ln: Optional[LineBox] = None
    prev_indent: Optional[int] = None

    for idx, ln in indexed:
        if prev_ln is None:
            cur_line_idxs.append(idx)
            cur_lines.append(ln)
            prev_ln = ln
            prev_indent = ln.x1
            continue

        gap = ln.y1 - prev_ln.y2
        indent_diff = abs(ln.x1 - (prev_indent if prev_indent is not None else ln.x1))

        if gap > gap_tol or indent_diff > indent_tol:
            flush_block()

        cur_line_idxs.append(idx)
        cur_lines.append(ln)
        prev_ln = ln
        prev_indent = ln.x1

    flush_block()
    return order_blocks_reading(blocks)


# -----------------------------
# Header/Footer tagging (repeating blocks)
# -----------------------------

def _norm_sig(text: str, max_len: int = 120) -> str:
    t = (text or "").lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:max_len]


def tag_headers_footers(pages) -> None:
    """
    Mutates pages in-place:
    - finds repeating block signatures near top/bottom across pages
    - tags those blocks as header/footer
    """
    if not pages or len(pages) < 2:
        return

    top_counts: Dict[str, int] = {}
    bot_counts: Dict[str, int] = {}
    page_info: List[Tuple[int, int, int]] = []  # (page_index, top_limit, bottom_limit)

    for pi, p in enumerate(pages):
        blocks = getattr(p, "blocks", None)
        if not blocks:
            page_info.append((pi, 0, 0))
            continue

        page_h = max(b.y2 for b in blocks) if blocks else 0
        if page_h <= 0:
            page_info.append((pi, 0, 0))
            continue

        top_limit = int(page_h * 0.12)
        bottom_limit = int(page_h * 0.88)
        page_info.append((pi, top_limit, bottom_limit))

        for b in blocks[:8]:
            if b.y1 <= top_limit:
                sig = _norm_sig(b.text)
                if sig:
                    top_counts[sig] = top_counts.get(sig, 0) + 1

        for b in blocks[-8:]:
            if b.y2 >= bottom_limit:
                sig = _norm_sig(b.text)
                if sig:
                    bot_counts[sig] = bot_counts.get(sig, 0) + 1

    for pi, top_limit, bottom_limit in page_info:
        p = pages[pi]
        blocks = getattr(p, "blocks", None)
        if not blocks:
            continue

        for b in blocks:
            sig = _norm_sig(b.text)
            if not sig:
                continue

            if b.y1 <= top_limit and top_counts.get(sig, 0) >= 2:
                b.block_type = "header"
                continue

            if b.y2 >= bottom_limit and bot_counts.get(sig, 0) >= 2:
                b.block_type = "footer"
                continue


# -----------------------------
# Basic Table Detection (from lines)
# -----------------------------

def detect_tables_from_lines(lines: List[LineBox]) -> List[TableBox]:
    """
    Basic table detection:
    - tables often have many short lines with aligned left edges (columns)
    - group consecutive lines with similar binned x1
    """
    if not lines or len(lines) < 6:
        return []

    indexed = list(enumerate(lines))
    indexed.sort(key=lambda it: (it[1].y1, it[1].x1))

    heights = sorted(max(1, ln.y2 - ln.y1) for _, ln in indexed)
    median_h = heights[len(heights) // 2]
    row_gap_tol = max(10, int(median_h * 1.2))

    def bin_x(x: int, bin_size: int = 20) -> int:
        return int(round(x / bin_size) * bin_size)

    tables: List[TableBox] = []

    cur_idxs: List[int] = []
    cur_lines: List[LineBox] = []
    cur_bins: List[int] = []
    prev_ln: Optional[LineBox] = None

    def flush():
        nonlocal cur_idxs, cur_lines, cur_bins, tables
        if len(cur_lines) < 6:
            cur_idxs, cur_lines, cur_bins = [], [], []
            return

        uniq = sorted(set(cur_bins))
        if len(uniq) < 2:
            cur_idxs, cur_lines, cur_bins = [], [], []
            return

        x1 = min(l.x1 for l in cur_lines)
        y1 = min(l.y1 for l in cur_lines)
        x2 = max(l.x2 for l in cur_lines)
        y2 = max(l.y2 for l in cur_lines)
        text = "\n".join(l.text for l in cur_lines).strip()

        tables.append(
            TableBox(
                text=text,
                x1=int(x1),
                y1=int(y1),
                x2=int(x2),
                y2=int(y2),
                line_indexes=cur_idxs.copy(),
            )
        )
        cur_idxs, cur_lines, cur_bins = [], [], []

    for idx, ln in indexed:
        ln_len = len((ln.text or "").strip())
        if ln_len > 140:
            flush()
            prev_ln = ln
            continue

        bx = bin_x(ln.x1)

        if not cur_lines:
            cur_idxs.append(idx)
            cur_lines.append(ln)
            cur_bins.append(bx)
            prev_ln = ln
            continue

        gap = ln.y1 - (prev_ln.y2 if prev_ln else ln.y1)
        if gap > row_gap_tol:
            flush()

        cur_idxs.append(idx)
        cur_lines.append(ln)
        cur_bins.append(bx)
        prev_ln = ln

    flush()
    return tables


def _in_bbox(w: WordBox, x1: int, y1: int, x2: int, y2: int) -> bool:
    # word center must be inside bbox
    cx = (w.x1 + w.x2) / 2.0
    cy = (w.y1 + w.y2) / 2.0
    return (x1 <= cx <= x2) and (y1 <= cy <= y2)


def structure_table_from_words(words: List[WordBox], table: TableBox) -> TableBox:
    """
    Build a simple grid for a detected table using word bboxes.
    Output:
      table.rows = [[cell, cell, ...], ...]
      table.n_rows, table.n_cols
    Heuristic:
      - filter words inside table bbox
      - cluster by Y to form rows
      - cluster by X to form columns
      - assign each word into nearest (row, col)
    """
    if not words:
        return table

    x1, y1, x2, y2 = table.x1, table.y1, table.x2, table.y2

    inside = [w for w in words if (w.text or "").strip() and _in_bbox(w, x1, y1, x2, y2)]
    if len(inside) < 8:
        return table

    # --- Compute median word height -> row tolerance
    heights = sorted(max(1, w.y2 - w.y1) for w in inside)
    med_h = heights[len(heights) // 2]
    row_tol = max(8, int(med_h * 0.9))

    # Helper: word centers
    def cy(w: WordBox) -> float:
        return (w.y1 + w.y2) / 2.0

    def cx(w: WordBox) -> float:
        return (w.x1 + w.x2) / 2.0

    # --- 1) Build row bands by clustering Y centers
    inside.sort(key=lambda w: (cy(w), w.x1))
    row_centers: List[float] = []
    row_words: List[List[WordBox]] = []

    for w in inside:
        placed = False
        for ri in range(max(0, len(row_centers) - 6), len(row_centers)):
            if abs(cy(w) - row_centers[ri]) <= row_tol:
                row_words[ri].append(w)
                # update running center
                row_centers[ri] = (row_centers[ri] * (len(row_words[ri]) - 1) + cy(w)) / len(row_words[ri])
                placed = True
                break
        if not placed:
            row_centers.append(cy(w))
            row_words.append([w])

    # sort rows top-to-bottom
    rows_sorted = sorted(zip(row_centers, row_words), key=lambda t: t[0])
    row_words = [rw for _, rw in rows_sorted]

    if len(row_words) < 2:
        return table

    # --- 2) Estimate column centers using X clustering across all words
    xs = sorted(cx(w) for w in inside)
    if not xs:
        return table

    # Column tolerance based on typical word width
    widths = sorted(max(1, w.x2 - w.x1) for w in inside)
    med_w = widths[len(widths) // 2]
    col_tol = max(18, int(med_w * 1.2))

    col_centers: List[float] = []
    for x in xs:
        placed = False
        for ci in range(len(col_centers)):
            if abs(x - col_centers[ci]) <= col_tol:
                # update center lightly
                col_centers[ci] = (col_centers[ci] * 0.8) + (x * 0.2)
                placed = True
                break
        if not placed:
            col_centers.append(x)

    col_centers = sorted(col_centers)

    # Keep columns reasonable (avoid huge counts on noisy docs)
    if len(col_centers) > 20:
        col_centers = col_centers[:20]

    n_cols = len(col_centers)
    if n_cols < 2:
        return table

    # --- 3) Assign words into (row, col)
    grid: List[List[List[WordBox]]] = [[[] for _ in range(n_cols)] for __ in range(len(row_words))]

    def nearest_col(x: float) -> int:
        best_i = 0
        best_d = abs(x - col_centers[0])
        for i in range(1, n_cols):
            d = abs(x - col_centers[i])
            if d < best_d:
                best_d = d
                best_i = i
        return best_i

    for r_idx, rw in enumerate(row_words):
        for w in rw:
            c_idx = nearest_col(cx(w))
            grid[r_idx][c_idx].append(w)

    # --- 4) Convert to rows of cell strings
    out_rows: List[List[str]] = []
    for r in range(len(grid)):
        row_cells: List[str] = []
        for c in range(n_cols):
            cell_words = grid[r][c]
            cell_words.sort(key=lambda w: w.x1)
            cell_text = " ".join(w.text for w in cell_words).strip()
            row_cells.append(cell_text)
        # drop fully empty rows
        if any(cell.strip() for cell in row_cells):
            out_rows.append(row_cells)

    # Optional: trim trailing empty columns for cleaner output
    # find last non-empty column index across all rows
    last_non_empty = -1
    for c in range(n_cols):
        if any((r[c] or "").strip() for r in out_rows):
            last_non_empty = c
    if last_non_empty >= 0:
        out_rows = [r[: last_non_empty + 1] for r in out_rows]
        n_cols = last_non_empty + 1

    table.rows = out_rows
    table.n_rows = len(out_rows)
    table.n_cols = n_cols
    return table
