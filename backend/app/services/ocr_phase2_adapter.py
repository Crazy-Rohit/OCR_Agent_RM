from __future__ import annotations

from typing import Any, Dict

from app.services.layout_service import build_layout


def phase2_enrich_page(page: Dict[str, Any]) -> Dict[str, Any]:
    """Phase 2: layout refinement only (NO dropping)."""
    words = page.get("words") or []
    layout = build_layout(words, page_width=page.get("width"), page_height=page.get("height"))

    out = dict(page)
    out["lines"] = layout.get("lines", [])
    out["blocks"] = layout.get("blocks", [])
    out["tables"] = layout.get("tables", [])
    out["text"] = layout.get("text") or (out.get("text") or "")

    out["stats"] = {
        **(out.get("stats") or {}),
        "phase2_layout": True,
        "total_words": len(words),
        "lines": len(out["lines"]),
        "blocks": len(out["blocks"]),
    }
    return out
