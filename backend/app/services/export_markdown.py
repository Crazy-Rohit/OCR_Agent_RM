from __future__ import annotations

from typing import List, Dict, Any, Optional


def _table_to_markdown(table: Dict[str, Any]) -> str:
    n_rows = int(table.get("n_rows") or 0)
    n_cols = int(table.get("n_cols") or 0)
    cells = table.get("cells") or []
    grid = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    for c in cells:
        r = int(c.get("row") or 0)
        k = int(c.get("col") or 0)
        if 0 <= r < n_rows and 0 <= k < n_cols:
            txt = (c.get("text") or "").replace("\n", " ").strip()
            grid[r][k] = txt

    # header separator: treat first row as header if looks like labels
    def is_headerish(row: List[str]) -> bool:
        non_empty = [x for x in row if x.strip()]
        if len(non_empty) < max(2, n_cols // 2):
            return False
        # header tends to be shorter
        avg_len = sum(len(x) for x in non_empty) / max(1, len(non_empty))
        return avg_len <= 18

    header = 0 if (n_rows >= 2 and is_headerish(grid[0])) else None

    lines: List[str] = []
    if n_rows == 0 or n_cols == 0:
        return ""

    def row_line(row: List[str]) -> str:
        safe = [x.replace("|", "\\|") for x in row]
        return "| " + " | ".join(safe) + " |"

    lines.append(row_line(grid[0]))
    if header is not None:
        lines.append("| " + " | ".join(["---"] * n_cols) + " |")
        start = 1
    else:
        lines.append("| " + " | ".join(["---"] * n_cols) + " |")
        start = 1

    for r in range(start, n_rows):
        lines.append(row_line(grid[r]))

    return "\n".join(lines)


def document_to_markdown(
    pages: List[Dict[str, Any]],
    *,
    tables: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Render normalized document blocks to Markdown (predictable + table-aware)."""
    md_parts: List[str] = []

    tables_by_page_block: Dict[str, Dict[str, Any]] = {}
    if tables:
        for t in tables:
            pn = int(t.get("page_number") or 0)
            bi = t.get("source_block_index")
            if bi is None:
                continue
            tables_by_page_block[f"{pn}:{int(bi)}"] = t

    for p in pages:
        page_num = int(p.get("page_number") or p.get("page") or 0)
        blocks = p.get("blocks", [])
        for bi, b in enumerate(blocks):
            # if we have an extracted table for this block, render it as markdown table
            key = f"{page_num}:{bi}"
            if key in tables_by_page_block:
                md = _table_to_markdown(tables_by_page_block[key])
                if md.strip():
                    md_parts.append(md)
                    continue

            btype = b.get("type", "paragraph")
            txt = (b.get("text_normalized") or b.get("text") or "").strip()
            if not txt:
                continue

            if btype == "heading":
                level = int(b.get("level") or 1)
                level = min(max(level, 1), 3)
                md_parts.append("#" * level + " " + txt)
            elif btype == "list_item":
                marker = b.get("marker") or "-"
                if marker.endswith(".") and marker[:-1].isdigit():
                    md_parts.append(f"{marker} {txt}")
                else:
                    md_parts.append(f"- {txt}")
            elif btype == "table_region":
                # fallback if table extraction didn't produce grid
                md_parts.append("```")
                md_parts.append(txt)
                md_parts.append("```")
            else:
                md_parts.append(txt)

        md_parts.append("")  # page separator newline

    return "\n".join(md_parts).strip()
