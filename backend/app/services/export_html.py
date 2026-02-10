from __future__ import annotations

from typing import Any, Dict, List, Optional
import html


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _table_to_html(table: Dict[str, Any]) -> str:
    n_rows = int(table.get("n_rows") or 0)
    n_cols = int(table.get("n_cols") or 0)
    cells = table.get("cells") or []
    header_rows = set(int(r) for r in (table.get("header_rows") or []))

    # Build a cell map for span-aware rendering
    cell_map: Dict[tuple[int, int], Dict[str, Any]] = {}
    for c in cells:
        r = int(c.get("row") or 0)
        k = int(c.get("col") or 0)
        if 0 <= r < n_rows and 0 <= k < n_cols:
            cell_map[(r, k)] = c

    # mark covered cells due to spans
    covered = [[False for _ in range(n_cols)] for _ in range(n_rows)]
    for (r, k), c in cell_map.items():
        rs = max(1, int(c.get("rowspan") or 1))
        cs = max(1, int(c.get("colspan") or 1))
        for rr in range(r, min(n_rows, r + rs)):
            for cc in range(k, min(n_cols, k + cs)):
                if (rr, cc) != (r, k):
                    covered[rr][cc] = True

    out: List[str] = []
    out.append("<table>")
    for r in range(n_rows):
        out.append("<tr>")
        for k in range(n_cols):
            if covered[r][k]:
                continue
            c = cell_map.get((r, k))
            text = (c.get("text") or "").strip() if c else ""
            rs = max(1, int(c.get("rowspan") or 1)) if c else 1
            cs = max(1, int(c.get("colspan") or 1)) if c else 1
            is_header = bool((r in header_rows) or (c and c.get("is_header") is True))
            tag = "th" if is_header else "td"
            attrs = ""
            if rs > 1:
                attrs += f" rowspan='{rs}'"
            if cs > 1:
                attrs += f" colspan='{cs}'"
            out.append(f"<{tag}{attrs}>{_esc(text)}</{tag}>")
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def document_to_html(
    pages: List[Dict[str, Any]],
    *,
    tables: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Simple HTML export: headings, paragraphs, lists, and extracted tables."""
    tables_by_page_block: Dict[str, Dict[str, Any]] = {}
    if tables:
        for t in tables:
            pn = int(t.get("page_number") or 0)
            bi = t.get("source_block_index")
            if bi is None:
                continue
            tables_by_page_block[f"{pn}:{int(bi)}"] = t

    out: List[str] = []
    out.append("<div class='ocr-document'>")
    for p in pages:
        page_num = int(p.get("page_number") or p.get("page") or 0)
        out.append(f"<section class='ocr-page' data-page='{page_num}'>")
        for bi, b in enumerate(p.get('blocks', []) or []):
            key = f"{page_num}:{bi}"
            if key in tables_by_page_block:
                out.append(_table_to_html(tables_by_page_block[key]))
                continue

            btype = (b.get("type") or "paragraph").lower()
            txt = (b.get("text_normalized") or b.get("text") or "").strip()
            if not txt:
                continue

            if btype == "heading":
                level = int(b.get("level") or 1)
                level = min(max(level, 1), 3)
                out.append(f"<h{level}>{_esc(txt)}</h{level}>")
            elif btype == "list_item":
                out.append(f"<li>{_esc(txt)}</li>")
            else:
                out.append(f"<p>{_esc(txt)}</p>")
        out.append("</section>")
    out.append("</div>")
    return "".join(out)
