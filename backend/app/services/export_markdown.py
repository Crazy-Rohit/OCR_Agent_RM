from __future__ import annotations

from typing import List, Dict, Any


def document_to_markdown(pages: List[Dict[str, Any]]) -> str:
    """Render normalized document blocks to Markdown (simple, predictable)."""
    md_parts: List[str] = []

    for p in pages:
        blocks = p.get("blocks", [])
        for b in blocks:
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
                # normalize marker: use '-' for bullets, '1.' for numbered
                if marker.endswith(".") and marker[:-1].isdigit():
                    md_parts.append(f"{marker} {txt}")
                else:
                    md_parts.append(f"- {txt}")
            elif btype == "table_region":
                # keep as fenced block for now
                md_parts.append("```")
                md_parts.append(txt)
                md_parts.append("```")
            else:
                md_parts.append(txt)

        md_parts.append("")  # page separator newline

    return "\n".join(md_parts).strip()
