from __future__ import annotations

from typing import Any, Dict, List


def mark_table_candidates(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Very lightweight heuristic:
    - If many lines have multiple big gaps (simulated by multiple spaces) OR
      if there are many numeric tokens aligned (approx)
    This only sets block['table_candidate']=True and block['type']='table_region' when strong.
    """
    out = []
    for b in blocks or []:
        text = (b.get("text") or "")
        lines = text.splitlines()
        if not lines:
            out.append(b)
            continue

        multi_space_lines = sum(1 for ln in lines if "  " in ln)
        numeric_tokens = sum(1 for tok in text.replace("\n", " ").split() if tok.strip(".,()").isdigit())

        strong = (multi_space_lines >= max(2, int(0.5 * len(lines)))) and (numeric_tokens >= 6)
        b2 = dict(b)
        if strong:
            b2["table_candidate"] = True
            b2["type"] = "table_region"
        else:
            b2["table_candidate"] = False
        out.append(b2)
    return out
