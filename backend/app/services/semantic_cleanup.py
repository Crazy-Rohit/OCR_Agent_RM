from __future__ import annotations

import re
from typing import Dict, Any, List


_HYPHEN_BREAK = re.compile(r"(\w)[-‐‑–](\s*)\n(\s*)(\w)")  # join hyphenated line-breaks
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")


def normalize_text(text: str) -> str:
    if not text:
        return ""

    # join hyphenated line breaks: "exam-\nple" -> "example"
    text = _HYPHEN_BREAK.sub(r"\1\4", text)

    # normalize spaces around punctuation
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)

    # normalize multiple spaces
    text = _MULTI_SPACE.sub(" ", text)

    # normalize excessive blank lines (keep max 2)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def cleanup_page(page: Dict[str, Any]) -> Dict[str, Any]:
    """Phase 3 (early): semantic cleanup without changing structure."""
    out = dict(page)
    out["text_normalized"] = normalize_text(out.get("text") or "")
    out["stats"] = {**(out.get("stats") or {}), "phase3_cleanup": True}
    return out
