import io
import os
import platform
import time
import uuid
from typing import List, Tuple

import pytesseract
from pytesseract import Output
import pypdfium2 as pdfium
from PIL import Image, ImageOps, ImageFilter
from docx import Document

from app.models.schemas import OCRResponse, PageText, WordBox
from app.services import file_service
from app.services import layout_service
from app.core.config import settings


# ---------------------------------------------------------
# Tesseract configuration (Windows-safe)
# ---------------------------------------------------------

def configure_tesseract():
    env_cmd = os.getenv("TESSERACT_CMD")
    if env_cmd and os.path.exists(env_cmd):
        pytesseract.pytesseract.tesseract_cmd = env_cmd
        return

    if platform.system().lower().startswith("win"):
        win_default = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(win_default):
            pytesseract.pytesseract.tesseract_cmd = win_default
            return


configure_tesseract()


def ocr_image(image: Image.Image) -> str:
    """Fast OCR without word boxes."""
    image = image.convert("L")

    w, h = image.size
    max_side = max(w, h)
    if max_side < 1000:
        scale = 1000 / max_side
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    image = ImageOps.autocontrast(image)
    image = image.filter(ImageFilter.SHARPEN)

    text = pytesseract.image_to_string(image)
    return text.strip()


def ocr_image_with_words(image: Image.Image) -> Tuple[str, List[WordBox]]:
    """OCR + word-level bounding boxes and confidence."""
    image = image.convert("L")

    w, h = image.size
    max_side = max(w, h)
    if max_side < 1000:
        scale = 1000 / max_side
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    image = ImageOps.autocontrast(image)
    image = image.filter(ImageFilter.SHARPEN)

    data = pytesseract.image_to_data(image, output_type=Output.DICT)
    words: List[WordBox] = []

    n = len(data.get("text", []))
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue

        conf = None
        try:
            conf_raw = data["conf"][i]
            if conf_raw not in (None, "", "-1"):
                conf = float(conf_raw)
        except Exception:
            conf = None

        x = int(data["left"][i])
        y = int(data["top"][i])
        ww = int(data["width"][i])
        hh = int(data["height"][i])

        words.append(
            WordBox(
                text=txt,
                x1=x,
                y1=y,
                x2=x + ww,
                y2=y + hh,
                confidence=conf,
            )
        )

    text = pytesseract.image_to_string(image).strip()
    return text, words


def extract_from_pdf(file_bytes: bytes, enable_layout: bool) -> List[PageText]:
    """
    Hybrid PDF:
    - Try text layer first
    - If empty, render and OCR
    - If enable_layout=True => words/lines/blocks/tables filled for OCR pages
    """
    pdf = pdfium.PdfDocument(file_bytes)
    pages: List[PageText] = []

    for i in range(len(pdf)):
        page = pdf[i]

        text = ""
        try:
            textpage = page.get_textpage()
            text = (textpage.get_text_range() or "").strip()
        except Exception:
            text = ""

        if not text:
            scale = 300 / 72.0
            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()

            if enable_layout:
                text, words = ocr_image_with_words(pil_image)
                lines = layout_service.words_to_lines(words) if words else None
                blocks = layout_service.lines_to_blocks(lines) if lines else None
                tables = layout_service.detect_tables_from_lines(lines) if lines else None

# ✅ NEW: build structured rows/cols using word boxes
            if tables and words:
                structured = []
                for t in tables:
                    structured.append(layout_service.structure_table_from_words(words, t))
                tables = structured

                pages.append(
                    PageText(
                        page_number=i + 1,
                        text=text,
                        words=words,
                        lines=lines,
                        blocks=blocks,
                        tables=tables,
                    )
                )
            else:
                text = ocr_image(pil_image)
                pages.append(
                    PageText(
                        page_number=i + 1,
                        text=text,
                        words=None,
                        lines=None,
                        blocks=None,
                        tables=None,
                    )
                )
        else:
            pages.append(
                PageText(
                    page_number=i + 1,
                    text=text,
                    words=None,
                    lines=None,
                    blocks=None,
                    tables=None,
                )
            )

    return pages


def extract_from_image(file_bytes: bytes, enable_layout: bool) -> List[PageText]:
    image = Image.open(io.BytesIO(file_bytes))

    if enable_layout:
        text, words = ocr_image_with_words(image)
        lines = layout_service.words_to_lines(words) if words else None
        blocks = layout_service.lines_to_blocks(lines) if lines else None
        tables = layout_service.detect_tables_from_lines(lines) if lines else None
        return [
            PageText(
                page_number=1,
                text=text,
                words=words,
                lines=lines,
                blocks=blocks,
                tables=tables,
            )
        ]

    # layout disabled => smaller payload, faster
    text = ocr_image(image)
    return [PageText(page_number=1, text=text, words=None, lines=None, blocks=None, tables=None)]


def extract_from_docx(file_bytes: bytes) -> List[PageText]:
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs)
    return [PageText(page_number=1, text=text, words=None, lines=None, blocks=None, tables=None)]


def process_file(
    file_bytes: bytes,
    filename: str,
    document_type: str,
    *,
    zero_retention: bool | None = None,
    enable_layout: bool = True,
) -> OCRResponse:
    start = time.time()
    job_id = str(uuid.uuid4())

    if zero_retention is None:
        zero_retention = settings.ZERO_RETENTION_DEFAULT

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        pages = extract_from_pdf(file_bytes, enable_layout=enable_layout)
    elif ext in {"jpg", "jpeg", "png", "bmp", "tif", "tiff"}:
        pages = extract_from_image(file_bytes, enable_layout=enable_layout)
    elif ext == "docx":
        pages = extract_from_docx(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: .{ext or 'unknown'}")

    # Tag repeating headers/footers only when layout exists
    if enable_layout:
        try:
            layout_service.tag_headers_footers(pages)
        except Exception:
            pass

    full_text = "\n\n".join(p.text for p in pages)
    processing_time_ms = int((time.time() - start) * 1000)

    if not zero_retention:
        file_service.save_unique_by_name(filename, file_bytes)
    else:
        file_service.delete_if_exists(filename)

    return OCRResponse(
        job_id=job_id,
        status="success",
        document_type=document_type,
        pages=pages,
        full_text=full_text,
        metadata={
            "file_name": filename,
            "file_type": ext,
            "num_pages": len(pages),
            "processing_time_ms": processing_time_ms,
            "engine": "tesseract",
            "zero_retention": bool(zero_retention),
            "enable_layout": bool(enable_layout),
        },
    )
