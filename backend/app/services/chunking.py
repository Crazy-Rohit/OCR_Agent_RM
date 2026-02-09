from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import hashlib


def _stable_id(text: str, page_number: int, block_indices: List[int]) -> str:
    h = hashlib.sha1()
    h.update(str(page_number).encode("utf-8"))
    h.update((",".join(map(str, block_indices))).encode("utf-8"))
    h.update(text.strip().encode("utf-8"))
    return h.hexdigest()[:16]


def chunk_document(
    pages: List[Dict[str, Any]],
    *,
    max_chars: int = 900,
    overlap_chars: int = 120,
) -> List[Dict[str, Any]]:
    """
    RAG-ready chunking (structure-aware, fast).
    - Chunks are made from block texts (normalized if available)
    - Keeps metadata: page_number, block_indices
    - Adds stable chunk_id
    """
    chunks: List[Dict[str, Any]] = []

    for p in pages:
        page_num = int(p.get("page_number") or 0)
        blocks = p.get("blocks") or []
        buf = ""
        buf_blocks: List[int] = []
        for i, b in enumerate(blocks):
            txt = (b.get("text_normalized") or b.get("text") or "").strip()
            if not txt:
                continue
            # add separator between blocks
            add = (txt + "\n").strip() + "\n"
            if len(buf) + len(add) > max_chars and buf.strip():
                chunk_text = buf.strip()
                chunks.append(
                    {
                        "chunk_id": _stable_id(chunk_text, page_num, buf_blocks),
                        "page_number": page_num,
                        "block_indices": buf_blocks[:],
                        "text": chunk_text,
                    }
                )
                # overlap
                if overlap_chars > 0:
                    buf = chunk_text[-overlap_chars:] + "\n"
                else:
                    buf = ""
                buf_blocks = []
            buf += add
            buf_blocks.append(i)

        if buf.strip():
            chunk_text = buf.strip()
            chunks.append(
                {
                    "chunk_id": _stable_id(chunk_text, page_num, buf_blocks),
                    "page_number": page_num,
                    "block_indices": buf_blocks[:],
                    "text": chunk_text,
                }
            )

    return chunks
