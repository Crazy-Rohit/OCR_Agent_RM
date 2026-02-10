from __future__ import annotations

import re
from typing import Tuple, Optional

_HYPHEN_BREAK = re.compile(r"(\w)[‐‑‒–-]\s*\n\s*(\w)")
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
_TRAILING_SPACES = re.compile(r"[ \t]+\n")
_MULTI_BLANK = re.compile(r"\n{3,}")

_LIST_MARKER = re.compile(r"^\s*(?P<marker>(?:\[\s*[xX ]\s*\])|(?:[☐☑☒])|(?:[-•*])|(?:\d+\.)|(?:\([a-zA-Z0-9]+\))|(?:[a-zA-Z]\)))\s+")


def split_list_marker(text: str) -> Tuple[Optional[str], str]:
    """Return (marker, rest) for list-like lines."""
    if not text:
        return None, ""
    m = _LIST_MARKER.match(text)
    if not m:
        return None, text.strip()
    marker = m.group("marker")
    rest = text[m.end():].strip()
    return marker, rest


def normalize_text(text: str) -> str:
    if not text:
        return ""

    # join hyphenated line breaks: "exam-\nple" -> "example"
    text = _HYPHEN_BREAK.sub(r"\1\2", text)

    # normalize spaces around punctuation
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)

    # remove trailing spaces on lines
    text = _TRAILING_SPACES.sub("\n", text)

    # normalize multiple spaces
    text = _MULTI_SPACE.sub(" ", text)

    # normalize excessive blank lines
    text = _MULTI_BLANK.sub("\n\n", text)

    return text.strip()
