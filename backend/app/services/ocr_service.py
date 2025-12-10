import io
import time
import uuid
from typing import List

import pytesseract
import pypdfium2 as pdfium
from PIL import Image, ImageOps, ImageFilter
from docx import Document

from app.models.schemas import OCRResponse, PageText
from app.services import file_service


# ---------------------------------------------------------
# Tesseract configuration (Windows)
# ---------------------------------------------------------

# If Tesseract is not in PATH, set the full path here:
# Change this if your install location is different
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def ocr_image(image: Image.Image) -> str:
    """
    OCR for a single image using Tesseract, with simple preprocessing.
    Works for both document-style and general images reasonably well.
    """
    # 1) Convert to grayscale
    image = image.convert("L")

    # 2) Upscale small images to help Tesseract
    w, h = image.size
    max_side = max(w, h)
    if max_side < 1000:
        scale = 1000 / max_side
        new_size = (int(w * scale), int(h * scale))
        image = image.resize(new_size, Image.LANCZOS)

    # 3) Auto-contrast and slight sharpen
    image = ImageOps.autocontrast(image)
    image = image.filter(ImageFilter.SHARPEN)

    # 4) OCR with Tesseract
    text = pytesseract.image_to_string(image)
    return text.strip()


# ---------------------------------------------------------
# PDF / DOCX handlers
# ---------------------------------------------------------

def extract_from_pdf(file_bytes: bytes) -> List[PageText]:
    """
    Hybrid PDF extractor:
    1) Try to read text layer with pypdfium2.
    2) If page has no usable text, render to image and run Tesseract.
    """
    pdf = pdfium.PdfDocument(file_bytes)
    pages: List[PageText] = []

    n_pages = len(pdf)
    for i in range(n_pages):
        page = pdf[i]

        # --- Step 1: try direct text extraction ---
        text = ""
        try:
            textpage = page.get_textpage()
            text = textpage.get_text_range() or ""
        except Exception:
            text = ""

        text = text.strip()

        # --- Step 2: fallback to OCR if no meaningful text ---
        if not text:
            bitmap = page.render(scale=2.0)  # ~144 dpi
            pil_image = bitmap.to_pil()
            text = ocr_image(pil_image)

        pages.append(PageText(page_number=i + 1, text=text))

    return pages


def extract_from_image(file_bytes: bytes) -> List[PageText]:
    """
    Handle JPG/PNG/TIFF… files with Tesseract.
    """
    image = Image.open(io.BytesIO(file_bytes))
    text = ocr_image(image)
    return [PageText(page_number=1, text=text)]


def extract_from_docx(file_bytes: bytes) -> List[PageText]:
    """
    DOCX doesn't need OCR, we can read text directly.
    Treat the whole doc as a single 'page' in Phase 1.
    """
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs)
    return [PageText(page_number=1, text=text)]


# ---------------------------------------------------------
# Main entry used by FastAPI route
# ---------------------------------------------------------

def process_file(file_bytes: bytes, filename: str, document_type: str) -> OCRResponse:
    """
    Decide by extension which extractor to use,
    then assemble a standard OCRResponse object.
    """
    start = time.time()
    job_id = str(uuid.uuid4())

    ext = ""
    if "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()

    if ext == "pdf":
        pages = extract_from_pdf(file_bytes)
    elif ext in {"jpg", "jpeg", "png", "bmp", "tif", "tiff"}:
        pages = extract_from_image(file_bytes)
    elif ext == "docx":
        pages = extract_from_docx(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: .{ext or 'unknown'}")

    full_text = "\n\n".join(p.text for p in pages)

    processing_time_ms = int((time.time() - start) * 1000)

    # Optional: store original file for debugging / history
    file_service.save_file(job_id, filename, file_bytes)

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
        },
    )
