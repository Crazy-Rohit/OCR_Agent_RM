from __future__ import annotations

from typing import List, Optional

from app.models.schemas import BlockBox, LineBox, PageText, TableBox, WordBox


def _sort_words(words: List[WordBox]) -> List[WordBox]:
    return sorted(words, key=lambda w: (w.y1, w.x1, w.y2, w.x2))


def _sort_lines(lines: List[LineBox]) -> List[LineBox]:
    return sorted(lines, key=lambda l: (l.y1, l.x1, l.y2, l.x2))


def _sort_blocks(blocks: List[BlockBox]) -> List[BlockBox]:
    return sorted(blocks, key=lambda b: (b.y1, b.x1, b.y2, b.x2))


def _sort_tables(tables: List[TableBox]) -> List[TableBox]:
    return sorted(tables, key=lambda t: (t.y1, t.x1, t.y2, t.x2))


def normalize_page(page: PageText) -> PageText:
    words: Optional[List[WordBox]] = _sort_words(page.words) if page.words else None
    lines: Optional[List[LineBox]] = _sort_lines(page.lines) if page.lines else None
    blocks: Optional[List[BlockBox]] = _sort_blocks(page.blocks) if page.blocks else None
    tables: Optional[List[TableBox]] = _sort_tables(page.tables) if page.tables else None

    return PageText(
        page_number=page.page_number,
        text=page.text,
        words=words,
        lines=lines,
        blocks=blocks,
        tables=tables,
    )


def normalize_pages(pages: List[PageText]) -> List[PageText]:
    return [normalize_page(p) for p in pages]
