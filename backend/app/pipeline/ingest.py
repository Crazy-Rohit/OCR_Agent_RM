from __future__ import annotations

import io
from dataclasses import dataclass
from typing import List, Optional

import pypdfium2 as pdfium
from PIL import Image

from app.core.config import settings


@dataclass
class IngestedPage:
    page_number: int  # 1-based
    image: Image.Image
    text_layer: Optional[str] = None


def pdf_to_pages(file_bytes: bytes) -> List[IngestedPage]:
    pdf = pdfium.PdfDocument(file_bytes)
    pages: List[IngestedPage] = []

    scale = float(settings.PDF_RENDER_DPI) / 72.0

    for i in range(len(pdf)):
        page = pdf[i]

        text_layer = None
        try:
            tp = page.get_textpage()
            tl = (tp.get_text_range() or "").strip()
            text_layer = tl or None
        except Exception:
            text_layer = None

        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()

        pages.append(IngestedPage(page_number=i + 1, image=pil_image, text_layer=text_layer))

    return pages


def image_to_page(file_bytes: bytes) -> List[IngestedPage]:
    img = Image.open(io.BytesIO(file_bytes))
    return [IngestedPage(page_number=1, image=img, text_layer=None)]
