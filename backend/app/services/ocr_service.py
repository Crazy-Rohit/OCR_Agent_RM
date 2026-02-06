import io
import os
import platform
import time
import uuid
from typing import List, Dict, Any

import pytesseract
import pypdfium2 as pdfium
from PIL import Image, ImageOps, ImageFilter
from docx import Document
from pytesseract import Output

from app.models.schemas import OCRResponse, PageText
from app.services import file_service
from app.core.config import settings

# (Optional) if you already have layout_service, keep it. Otherwise remove these 2 lines.
from app.services.layout_service import build_layout


def configure_tesseract():
    env_cmd = os.getenv("TESSERACT_CMD")
    if env_cmd and os.path.exists(env_cmd):
        pytesseract.pytesseract.tesseract_cmd = env_cmd
        return

    if platform.system().lower().startswith("win"):
        win_default = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
        if os.path.exists(win_default):
            pytesseract.pytesseract.tesseract_cmd = win_default
            return


configure_tesseract()


def _preprocess(image: Image.Image) -> Image.Image:
    image = image.convert("L")

    w, h = image.size
    max_side = max(w, h)
    if max_side < 1000:
        scale = 1000 / max_side
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    image = ImageOps.autocontrast(image)
    image = image.filter(ImageFilter.SHARPEN)
    return image


def ocr_image_text_only(image: Image.Image) -> str:
    image = _preprocess(image)
    return pytesseract.image_to_string(image).strip()


def ocr_image_words(image: Image.Image) -> Dict[str, Any]:
    """OCR with word-level confidence + bbox."""
    image = _preprocess(image)
    data = pytesseract.image_to_data(image, output_type=Output.DICT)

    words: List[Dict[str, Any]] = []
    texts: List[str] = []

    n = len(data.get("text", []))
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        conf = data["conf"][i]

        if not txt or conf == "-1":
            continue

        try:
            conf_f = float(conf) / 100.0
        except Exception:
            conf_f = None

        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])

        words.append(
            {
                "text": txt,
                "confidence": conf_f,
                "bbox": [left, top, left + width, top + height],
            }
        )
        texts.append(txt)

    return {"text": " ".join(texts).strip(), "words": words}


def extract_from_pdf(file_bytes: bytes) -> List[PageText]:
    """Hybrid: text-layer PDF first; OCR fallback returns words+confidence."""
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

        if text:
            pages.append(PageText(page_number=i + 1, text=text))
        else:
            scale = 300 / 72.0
            bitmap = page.render(scale=scale)
            pil_image = bitmap.to_pil()

            o = ocr_image_words(pil_image)
            pages.append(PageText(page_number=i + 1, text=o["text"], words=o["words"]))

    return pages


def extract_from_image(file_bytes: bytes) -> List[PageText]:
    image = Image.open(io.BytesIO(file_bytes))
    o = ocr_image_words(image)
    return [PageText(page_number=1, text=o["text"], words=o["words"])]


def extract_from_docx(file_bytes: bytes) -> List[PageText]:
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\\n".join(paragraphs)
    return [PageText(page_number=1, text=text)]


def process_file(
    file_bytes: bytes,
    filename: str,
    document_type: str,
    *,
    zero_retention: bool | None = None,
) -> OCRResponse:
    start = time.time()
    job_id = str(uuid.uuid4())

    if zero_retention is None:
        zero_retention = settings.ZERO_RETENTION_DEFAULT

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        pages = extract_from_pdf(file_bytes)
    elif ext in {"jpg", "jpeg", "png", "bmp", "tif", "tiff"}:
        pages = extract_from_image(file_bytes)
    elif ext == "docx":
        pages = extract_from_docx(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: .{ext or 'unknown'}")

    full_text = "\\n\\n".join(p.text for p in pages)
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
        },
    )


def process_page(words):
    return build_layout(words)
